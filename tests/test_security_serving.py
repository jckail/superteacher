"""Static/SPA serving, response hygiene (errors, headers, caching) and configuration that must stay locked down."""

import re
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from superteacher import db as database
from tests.sec_util import H, build, login, seed_class

ROOT = Path(__file__).resolve().parent.parent
SECRET = "TOP-SECRET-OUTSIDE-DIST"


@pytest.fixture
def site(tmp_path):
    """A built SPA (dist/) with a secret file next to it, a sibling dir sharing its name prefix, and a symlink."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "sub").mkdir()
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (dist / "sub" / "page.txt").write_text("sub page")
    (tmp_path / "secret.txt").write_text(SECRET)
    (tmp_path / "dist-private").mkdir()
    (tmp_path / "dist-private" / "secret.txt").write_text(SECRET)
    (dist / "leak").symlink_to(tmp_path / "secret.txt")
    with build(static_dir=dist, raise_server_exceptions=False) as c:
        yield c


TRAVERSAL = [
    "/../secret.txt",
    "/..%2fsecret.txt",
    "/..%2Fsecret.txt",
    "/%2e%2e/secret.txt",
    "/%2e%2e%2fsecret.txt",
    "/%2E%2E/%2E%2E/secret.txt",
    "/assets/../../secret.txt",
    "/assets/..%2f..%2fsecret.txt",
    "/assets/%2e%2e/%2e%2e/secret.txt",
    "/..%5csecret.txt",
    "/..\\secret.txt",
    "/\\..\\secret.txt",
    "//secret.txt",
    "///etc/passwd",
    "/../dist-private/secret.txt",
    "/..%2fdist-private%2fsecret.txt",
    "/%252e%252e/secret.txt",
    "/....//secret.txt",
    "/.%2e/secret.txt",
    "/..;/secret.txt",
    "/leak",  # symlink pointing outside dist
    "/etc/passwd",
    "/proc/self/environ",
    "/%c0%ae%c0%ae/secret.txt",
    "/‥/secret.txt",
]


# NUL bytes: the SPA handler calls Path.resolve(), which raises ValueError -> an unauthenticated bare 500 (F-10).
NUL_PATHS = [
    pytest.param(
        p, marks=pytest.mark.xfail(reason="F-10: NUL byte in SPA path -> ValueError -> 500 (main.py)", strict=False)
    )
    for p in ("/%00", "/index.html%00.png", "/assets%00", "/a/%00/b")
]


@pytest.mark.parametrize("path", [*TRAVERSAL, *NUL_PATHS])
def test_no_path_traversal(site, path):
    r = site.get(path)
    assert SECRET not in r.text and "root:" not in r.text and "PATH=" not in r.text
    assert r.status_code in (200, 307, 400, 404)
    if r.status_code == 200:  # the SPA fallback is the only acceptable 200
        assert "<title>SPA</title>" in r.text


def test_spa_and_assets_are_served(site):
    assert "<title>SPA</title>" in site.get("/").text
    assert "<title>SPA</title>" in site.get("/students/abc123").text  # client-side route
    assert site.get("/assets/app.js").text == "console.log(1)"
    assert site.get("/sub/page.txt").text == "sub page"


def test_no_directory_listing(site):
    for p in ("/assets", "/assets/", "/sub", "/sub/", "/"):
        r = site.get(p, follow_redirects=True)
        assert "app.js" not in r.text and "page.txt" not in r.text and "Index of" not in r.text, p


def test_sensitive_files_are_not_reachable(site):
    for p in ("/.env", "/.session_secret", "/.git/config", "/superteacher/auth.py", "/data/superteacher.db",
              "/alembic.ini", "/requirements.txt", "/assets/app.js.map", "/server.py", "/Dockerfile"):  # fmt: skip
        r = site.get(p)
        assert "AUTH_PASSWORD" not in r.text and "SESSION_SECRET" not in r.text and "sqlite" not in r.text.lower(), p
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            assert "<title>SPA</title>" in r.text


def test_session_secret_file_is_outside_any_served_directory(tmp_path):
    """The generated .session_secret lives next to the DB; the static root must never contain it."""
    assert not (ROOT / "web" / "dist" / ".session_secret").exists()
    assert not (ROOT / "web" / "public" / ".session_secret").exists()
    assert ".session_secret" in (ROOT / ".gitignore").read_text()


@pytest.mark.xfail(
    reason="F-09: the SPA catch-all (GET /{path:path}) also answers unknown /api/* GETs with index.html (200). "
    "Patch in main.py: 404 JSON for api/ paths (docs/SECURITY_REVIEW.md).",
    strict=False,
)
@pytest.mark.parametrize(
    "path", ["/api/nope", "/api/students/../x", "/api", "/api/", "/api/auth/nope", "/api/openapi.json"]
)
def test_unknown_api_paths_are_json_404_not_the_spa(site, path):
    r = site.get(path)
    assert r.status_code in (401, 404, 405)
    assert "<title>SPA</title>" not in r.text


def test_unknown_api_write_methods_do_not_fall_through_to_the_spa(site):
    for m in ("POST", "PUT", "DELETE", "PATCH"):
        assert site.request(m, "/api/nope", headers=H).status_code in (404, 405)


def test_vite_build_config_does_not_publish_source_maps():
    cfg = (ROOT / "web" / "vite.config.js").read_text()
    assert not re.search(r"sourcemap\s*:\s*(true|'inline'|\"inline\"|'hidden')", cfg)


def test_docker_context_excludes_secrets_and_data():
    ignore = (ROOT / ".dockerignore").read_text().splitlines()
    for needed in (".env", ".env.*", "*.db", "data/", ".git", "tests/"):
        assert needed in ignore, f".dockerignore must exclude {needed}"
    assert "USER app" in (ROOT / "Dockerfile").read_text()  # not root


# ── response hygiene ────────────────────────────────────────────────────
@pytest.fixture
def api():
    with build(raise_server_exceptions=False) as c:
        assert login(c).status_code == 200
        yield c


@pytest.mark.xfail(
    reason="F-04: no request body size cap; a 30 MB body is buffered and parsed before the 401 (main.py middleware)",
    strict=False,
)
def test_oversized_request_bodies_are_rejected_early(api):
    big = b'{"name":"' + b"x" * 8_000_000 + b'"}'
    r = api.post("/api/courses", content=big, headers={**H, "content-type": "application/json"})
    assert r.status_code == 413
    api.cookies.clear()
    r = api.post("/api/auth/login", content=b'{"password":"' + b"x" * 8_000_000 + b'"}', headers=H)
    assert r.status_code == 413


def test_unhandled_exception_body_is_generic(api):
    def boom():
        raise RuntimeError("secret detail at /home/app/superteacher/db.py line 12: SELECT * FROM students")

    api.app.add_api_route("/api/boom", boom, methods=["GET"])
    r = api.get("/api/boom")
    assert r.status_code == 500
    for leak in ("secret detail", "/home/app", "Traceback", "SELECT", "RuntimeError", "db.py"):
        assert leak not in r.text


def test_database_errors_do_not_leak_sql_or_paths(api):
    seed_class(api)

    def broken():
        raise OperationalError("SELECT students.secret FROM students", {}, Exception("unable to open /data/prod.db"))
        yield  # pragma: no cover

    saved = api.app.dependency_overrides[database.get_db]
    api.app.dependency_overrides[database.get_db] = broken
    try:
        for path in ("/api/students", "/api/overview", "/api/courses"):
            r = api.get(path)
            assert r.status_code == 500
            assert "SELECT" not in r.text and "/data" not in r.text and "OperationalError" not in r.text
    finally:
        api.app.dependency_overrides[database.get_db] = saved


def test_health_is_generic_when_the_database_is_down(api):
    class DeadSession:
        def execute(self, *_a, **_k):
            raise OperationalError("SELECT 1", {}, Exception("disk I/O error at /data/prod.db"))

    api.app.dependency_overrides[database.get_db] = lambda: DeadSession()
    r = api.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "unhealthy"
    assert "prod.db" not in r.text and "disk" not in r.text and r.json()["database"] == "error"


def test_validation_errors_do_not_leak_internals(api):
    r = api.post("/api/students", json={"name": "x"}, headers=H)
    assert r.status_code == 422
    assert "Traceback" not in r.text and "/superteacher/" not in r.text and "site-packages" not in r.text


def test_auth_error_messages_are_uniform(api):
    api.cookies.clear()
    a = api.get("/api/overview")
    b = api.get("/api/students/does-not-exist")
    assert a.status_code == b.status_code == 401 and a.json() == b.json() == {"detail": "Not authenticated"}


SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/health"),
        ("GET", "/api/version"),
        ("GET", "/api/overview"),  # 200 with a session
        ("GET", "/api/students/nope"),  # 404
        ("POST", "/api/courses"),  # 422 (no body)
        ("GET", "/api/auth/me"),
        ("POST", "/api/auth/login"),  # 403 (no csrf header)
    ],
)
def test_security_headers_on_every_api_response(api, method, path):
    r = api.request(method, path)
    for k, v in SECURITY_HEADERS.items():
        assert r.headers.get(k) == v, (path, k)
    csp = r.headers["content-security-policy"]
    for directive in ("default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'",
                      "form-action 'self'", "script-src 'self'"):  # fmt: skip
        assert directive in csp
    assert "unsafe-eval" not in csp and "script-src 'self' 'unsafe" not in csp and "*" not in csp.replace("'self'", "")
    assert r.headers["cache-control"] == "no-store"
    assert "server" not in {k.lower() for k in r.headers} or "uvicorn" not in r.headers["server"].lower()


def test_security_headers_on_spa_assets_and_404(site):
    for p in ("/", "/assets/app.js", "/students/x", "/definitely/missing.png"):
        r = site.get(p)
        assert r.headers["x-content-type-options"] == "nosniff", p
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"], p
        assert r.headers["x-frame-options"] == "DENY", p


def test_csv_download_is_not_cacheable_and_sniff_proof(api):
    ids = seed_class(api)
    r = api.get(f"/api/reports/sections/{ids['section']}/gradebook.csv")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment")


def test_docs_and_openapi_are_off_by_default(api):
    for p in ("/api/docs", "/api/redoc", "/api/openapi.json", "/docs", "/redoc", "/openapi.json"):
        r = api.get(p)
        assert "swagger" not in r.text.lower() and '"openapi"' not in r.text and "paths" not in r.text[:300], p
    assert api.app.openapi_url is None and api.app.docs_url is None and api.app.redoc_url is None


def test_docs_flag_is_opt_in_and_defaults_false():
    from superteacher.config import Settings

    assert Settings.model_fields["enable_docs"].default is False
    assert Settings.model_fields["auth_disabled"].default is False  # open mode must be an explicit choice


def test_start_refuses_without_a_passcode():
    from superteacher.config import Settings
    from superteacher.main import create_app

    with pytest.raises(RuntimeError, match="AUTH_PASSWORD"):
        create_app(settings=Settings(auth_password=None, auth_disabled=False))
    with pytest.raises(RuntimeError, match="AUTH_PASSWORD"):
        create_app(settings=Settings(auth_password="", auth_disabled=False))


def test_cors_defaults_are_not_wildcard():
    from superteacher.config import Settings

    assert "*" not in Settings().cors_origins
