"""Authentication behind a trusted TLS-terminating proxy uses the effective origin/IP."""

from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from superteacher import auth
from tests.test_auth import PW, H, make

HEADERS = {**H, "Origin": "https://testserver", "X-Forwarded-Proto": "https"}


def test_trusted_tls_proxy_preserves_browser_origin_and_secure_cookie():
    with make() as base:
        app = ProxyHeadersMiddleware(base.app, trusted_hosts="*")
        with TestClient(app, base_url="http://testserver") as proxied:
            response = proxied.post("/api/auth/login", json={"password": PW}, headers=HEADERS)
            assert response.status_code == 200
            assert "Secure" in response.headers["set-cookie"]


def test_untrusted_forwarded_scheme_cannot_change_same_origin_check():
    with make() as base:
        app = ProxyHeadersMiddleware(base.app, trusted_hosts="192.0.2.1")
        with TestClient(app, base_url="http://testserver") as proxied:
            assert proxied.post("/api/auth/login", json={"password": PW}, headers=HEADERS).status_code == 403


def test_proxy_clients_have_separate_login_lockouts():
    with make() as base:
        app = ProxyHeadersMiddleware(base.app, trusted_hosts="*")
        with TestClient(app, base_url="http://testserver") as proxied:
            noisy = {**HEADERS, "X-Forwarded-For": "203.0.113.7"}
            for _ in range(auth.MAX_FREE_ATTEMPTS + 1):
                proxied.post("/api/auth/login", json={"password": "wrong"}, headers=noisy)
            assert proxied.post("/api/auth/login", json={"password": PW}, headers=noisy).status_code == 429
            quiet = {**HEADERS, "X-Forwarded-For": "198.51.100.9"}
            assert proxied.post("/api/auth/login", json={"password": PW}, headers=quiet).status_code == 200
