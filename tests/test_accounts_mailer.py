"""Mailer backends. No real network: SendGrid goes through httpx.MockTransport; nothing here can send email."""

import asyncio
import json
import logging
import stat
import threading

import httpx
import pytest

from superteacher import mailer
from superteacher.config import Settings
from tests.acct_util import build, outbox, request_link

LINK = "http://testserver/auth/verify#token=SECRETTOKENSECRETTOKENSECRETTOKENSECRETTOKEN"
TO = "private.person@example.org"


def settings(**kw) -> Settings:
    base = {"auth_disabled": False, "auth_mode": "accounts", "sendgrid_api_key": "SG.fake-key-for-tests.zzzzzzzz",
            "auth_email_from": "noreply@demo.example", **kw}  # fmt: skip
    return Settings(**base)


def test_sendgrid_request_shape_and_no_tracking():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = (
            str(request.url),
            request.headers["authorization"],
            json.loads(request.content),
        )
        return httpx.Response(202)

    ok = mailer.send_login_link(settings(), TO, LINK, transport=httpx.MockTransport(handler))
    assert ok
    assert seen["url"] == "https://api.sendgrid.com/v3/mail/send"
    assert seen["auth"] == "Bearer SG.fake-key-for-tests.zzzzzzzz"
    body = seen["body"]
    assert body["personalizations"] == [{"to": [{"email": TO}]}] and body["from"] == {"email": "noreply@demo.example"}
    kinds = {c["type"]: c["value"] for c in body["content"]}
    assert LINK in kinds["text/plain"] and "ignore" in kinds["text/plain"].lower()
    assert LINK in kinds["text/html"]
    t = body["tracking_settings"]
    assert t["click_tracking"]["enable"] is False and t["open_tracking"]["enable"] is False


def test_sendgrid_failure_is_swallowed_and_logs_leak_nothing(caplog):
    def handler(_r):
        return httpx.Response(401, json={"errors": [{"message": f"bad key SG.fake-key-for-tests.zzzzzzzz for {TO}"}]})

    with caplog.at_level(logging.DEBUG):
        assert mailer.send_login_link(settings(), TO, LINK, transport=httpx.MockTransport(handler)) is False
    logs = caplog.text
    assert "RuntimeError" in logs
    for secret in (TO, "private.person", "SECRETTOKEN", "fake-key-for-tests", "SG."):
        assert secret not in logs


def test_sendgrid_network_error_is_swallowed(caplog):
    def boom(_r):
        raise httpx.ConnectError(f"cannot reach for {TO}")

    assert mailer.send_login_link(settings(), TO, LINK, transport=httpx.MockTransport(boom)) is False
    assert TO not in caplog.text


def test_console_backend_logs_a_redacted_notice_only(caplog):
    with caplog.at_level(logging.DEBUG):
        assert mailer.send_login_link(settings(auth_email_backend="console"), TO, LINK)
    assert "sign-in email generated" in caplog.text
    assert TO not in caplog.text and "SECRETTOKEN" not in caplog.text and "testserver" not in caplog.text


def test_file_backend_writes_the_message_privately(tmp_path):
    s = settings(auth_email_backend="file", auth_email_outbox_dir=str(tmp_path / "o"))
    assert mailer.send_login_link(s, TO, LINK)
    (f,) = (tmp_path / "o").glob("*.json")
    assert stat.S_IMODE(f.stat().st_mode) == 0o600
    msg = json.loads(f.read_text())
    assert msg["to"] == TO and LINK in msg["text"] and msg["subject"] == mailer.SUBJECT


def test_html_escapes_the_link():
    m = mailer.build_login_message(TO, 'http://x/auth/verify#token="><script>alert(1)</script>', 15)
    assert "<script>" not in m.html and "&lt;script&gt;" in m.html
    assert "15 minutes" in m.text and "synthetic" in m.text.lower()


@pytest.mark.parametrize("backend", ["console", "file"])
def test_insecure_backends_refused_in_production(monkeypatch, tmp_path, backend):
    monkeypatch.setenv("K_SERVICE", "superteacher")
    kw = {"auth_email_backend": backend, "auth_email_outbox_dir": str(tmp_path)}
    with pytest.raises(mailer.MailerConfigError, match="production"):
        mailer.validate_settings(settings(**kw))
    with pytest.raises(mailer.MailerConfigError):
        build(tmp_path, auth_email_backend=backend)  # the app refuses to start
    mailer.validate_settings(settings(**kw, auth_email_allow_insecure_backend=True))  # explicit override
    mailer.validate_settings(settings())  # sendgrid is fine in production


def test_insecure_backends_allowed_outside_production(monkeypatch, tmp_path):
    monkeypatch.delenv("K_SERVICE", raising=False)
    mailer.validate_settings(settings(auth_email_backend="console"))


def test_misconfiguration_fails_at_startup(tmp_path):
    with pytest.raises(mailer.MailerConfigError, match="SENDGRID_API_KEY"):
        build(tmp_path, auth_email_backend="sendgrid", sendgrid_api_key=None)
    with pytest.raises(mailer.MailerConfigError, match="OUTBOX"):
        build(tmp_path, auth_email_backend="file", auth_email_outbox_dir=None)


def test_endpoint_reply_is_identical_when_the_provider_fails(tmp_path, monkeypatch):
    real = httpx.Client

    def failing_client(*a, **k):
        k["transport"] = httpx.MockTransport(lambda r: httpx.Response(500))
        return real(*a, **k)

    monkeypatch.setattr(mailer.httpx, "Client", failing_client)
    with build(tmp_path, auth_email_backend="sendgrid", sendgrid_api_key="SG.fake-key-for-tests.zzzzzzzz",
               auth_email_from="n@demo.example") as c:  # fmt: skip
        r = request_link(c, "someone@example.com")
    assert r.status_code == 202 and r.json()["status"] == "ok"


def test_async_send_runs_off_the_event_loop(monkeypatch):
    seen = {}

    def fake(_settings, _to, _link, transport=None):
        seen["thread"] = threading.get_ident()
        return True

    monkeypatch.setattr(mailer, "send_login_link", fake)
    main = threading.get_ident()
    assert asyncio.run(mailer.send_login_link_async(settings(), TO, LINK)) is True
    assert seen["thread"] != main


def test_request_link_sends_via_file_backend(tmp_path):
    with build(tmp_path) as c:
        request_link(c, "Case@Example.com")
        (m,) = outbox(tmp_path)
        assert m["to"] == "case@example.com"
