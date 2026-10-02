"""Strict-Transport-Security is sent on HTTPS (directly or via the TLS-terminating proxy), never on plain HTTP."""

from fastapi.testclient import TestClient

HSTS = "Strict-Transport-Security"


def test_no_hsts_over_plain_http(client):
    assert HSTS not in client.get("/api/health").headers


def test_hsts_when_the_proxy_says_the_request_was_https(client):
    r = client.get("/api/health", headers={"X-Forwarded-Proto": "https"})
    assert r.headers[HSTS] == "max-age=15552000"
    assert "includeSubDomains" not in r.headers[HSTS] and "preload" not in r.headers[HSTS]  # the domain is shared


def test_hsts_on_a_direct_https_request(client):
    with TestClient(client.app, base_url="https://testserver") as https:
        assert https.get("/api/health").headers[HSTS] == "max-age=15552000"


def test_hsts_also_covers_static_and_error_responses(client):
    r = client.get("/api/nope", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 404 and HSTS in r.headers
