"""SMTP backend, the delivery circuit breaker, and honest behaviour when sign-in email is down.

Background (a real incident): SendGrid answered "Maximum credits exceeded", the app kept replying "a link is on its
way", and in accounts mode nobody could sign in. Now: the provider's reason is logged, repeated failures open a
breaker, and the sign-in endpoint answers 503 instead of a promise it cannot keep.
"""

import json
import logging
import smtplib
import ssl
from typing import ClassVar

import httpx
import pytest

from superteacher import mailer
from superteacher.config import Settings
from tests.acct_util import build, request_link

TO = "teacher@example.com"
LINK = "https://demo.example/auth/verify#token=SECRETTOKEN"


def settings(**kw) -> Settings:
    base = {
        "auth_mode": "accounts",
        "auth_disabled": False,
        "session_secret": "s" * 32,
        "auth_email_from": "from@example.org",
    }
    return Settings(**{**base, **kw})


# ── circuit breaker ─────────────────────────────────────────────────────────────────────────────────────────────
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_breaker_opens_after_consecutive_failures_and_closes_on_success():
    clock = Clock()
    h = mailer.DeliveryHealth(clock)
    assert h.available()
    for _ in range(mailer.DeliveryHealth.FAILURES - 1):
        h.record(False)
    assert h.available()  # one short of the threshold
    h.record(False)
    assert not h.available()
    h.record(True)  # a success (e.g. the half-open probe) closes it
    assert h.available()


def test_breaker_lets_a_probe_through_after_the_cooldown():
    clock = Clock()
    h = mailer.DeliveryHealth(clock)
    for _ in range(mailer.DeliveryHealth.FAILURES):
        h.record(False)
    assert not h.available()
    clock.t += mailer.DeliveryHealth.COOLDOWN - 1
    assert not h.available()
    clock.t += 2
    assert h.available()  # half-open
    h.record(False)  # the probe failed: closed for another cooldown
    assert not h.available()


def test_a_success_between_failures_resets_the_count():
    h = mailer.DeliveryHealth(Clock())
    for _ in range(10):
        h.record(False)
        h.record(False)
        h.record(True)
    assert h.available()


# ── provider reason is logged, secrets are not ──────────────────────────────────────────────────────────────────
def test_sendgrid_refusal_logs_the_providers_reason_but_no_key_or_address(caplog):
    key = "SG.supersecretkeyvalue1234567890"
    s = settings(auth_email_backend="sendgrid", sendgrid_api_key=key)
    transport = httpx.MockTransport(
        lambda r: httpx.Response(401, json={"errors": [{"message": "Maximum credits exceeded"}]})
    )
    with caplog.at_level(logging.ERROR, logger="superteacher.mailer"):
        assert mailer.send_login_link(s, TO, LINK, transport) is False
    assert "Maximum credits exceeded" in caplog.text and "401" in caplog.text
    assert key not in caplog.text and TO not in caplog.text and "SECRETTOKEN" not in caplog.text
    assert mailer.HEALTH._consecutive == 1


def test_provider_reason_is_bounded_and_tolerates_garbage():
    long = httpx.Response(400, json={"errors": [{"message": "x" * 1000}]})
    assert len(mailer.provider_reason(long)) <= 160
    assert mailer.provider_reason(httpx.Response(500, text="<html>not json</html>")) == ""
    assert mailer.provider_reason(httpx.Response(400, json={"errors": "nope"})) == ""


# ── SMTP backend ────────────────────────────────────────────────────────────────────────────────────────────────
class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []
    fail_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls: list[str] = []
        self.sent = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.tls_context = context

    def login(self, user, password):
        self.calls.append("login")
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials for secret-password")
        self.creds = (user, password)

    def send_message(self, msg):
        self.calls.append("send")
        self.sent = msg


@pytest.fixture
def fake_smtp(monkeypatch):
    FakeSMTP.instances.clear()
    FakeSMTP.fail_login = False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


def smtp_settings(**kw):
    return settings(
        auth_email_backend="smtp", smtp_host="smtp.example.org", smtp_username="user", smtp_password="pw", **kw
    )


def test_smtp_starttls_verifies_the_server_and_sends_text_and_html(fake_smtp):
    assert mailer.send_login_link(smtp_settings(), TO, LINK) is True
    (c,) = fake_smtp.instances
    assert (c.host, c.port) == ("smtp.example.org", 587) and c.timeout == 15
    assert c.calls == ["starttls", "login", "send"]  # TLS first, THEN credentials
    assert c.tls_context.verify_mode == ssl.CERT_REQUIRED and c.tls_context.check_hostname
    assert c.creds == ("user", "pw")
    msg = c.sent
    assert msg["To"] == TO and msg["From"] == "from@example.org" and msg["Subject"] == mailer.SUBJECT
    kinds = {p.get_content_type() for p in msg.walk()}
    assert {"text/plain", "text/html"} <= kinds and LINK in msg.get_body(("plain",)).get_content()
    assert mailer.HEALTH._consecutive == 0


def test_smtp_ssl_mode_and_no_credentials(fake_smtp):
    s = settings(auth_email_backend="smtp", smtp_host="smtp.example.org", smtp_port=465, smtp_security="ssl")
    assert mailer.send_login_link(s, TO, LINK)
    (c,) = fake_smtp.instances
    assert c.port == 465 and c.calls == ["send"]  # SMTP_SSL is TLS from the start; no AUTH without a username
    assert c.context.verify_mode == ssl.CERT_REQUIRED


def test_smtp_failure_is_swallowed_logged_by_type_and_leaks_nothing(fake_smtp, caplog):
    fake_smtp.fail_login = True
    with caplog.at_level(logging.ERROR, logger="superteacher.mailer"):
        assert mailer.send_login_link(smtp_settings(), TO, LINK) is False
    assert "SMTPAuthenticationError" in caplog.text
    assert "secret-password" not in caplog.text and TO not in caplog.text and "SECRETTOKEN" not in caplog.text
    assert mailer.HEALTH._consecutive == 1


@pytest.mark.parametrize("kw", [{"smtp_host": None}, {"auth_email_from": None}])
def test_smtp_needs_host_and_from(kw):
    s = settings(auth_email_backend="smtp", **{"smtp_host": "h", **kw})
    with pytest.raises(mailer.MailerConfigError, match="SMTP_HOST"):
        mailer.validate_settings(s)


def test_smtp_cannot_be_configured_without_tls():
    with pytest.raises(ValueError):
        Settings(auth_email_backend="smtp", smtp_security="none")  # type: ignore[arg-type]


# ── the endpoint is honest when delivery is down ────────────────────────────────────────────────────────────────
def break_delivery(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(mailer, "send", boom)


def test_signin_answers_503_after_repeated_delivery_failures_then_recovers(tmp_path, monkeypatch):
    with build(tmp_path) as c:
        assert c.get("/api/auth/config").json()["email_available"] is True
        original = mailer.send
        break_delivery(monkeypatch)
        for _ in range(mailer.DeliveryHealth.FAILURES):
            assert (
                request_link(c, TO).status_code == 202
            )  # the breaker is still learning: indistinguishable from success
        r = request_link(c, TO)
        assert r.status_code == 503 and "temporarily unavailable" in r.json()["detail"]
        assert r.headers["retry-after"] == "300"
        assert c.get("/api/auth/config").json()["email_available"] is False

        # same answer whatever the address (no enumeration through the breaker)
        assert request_link(c, "someone.else@example.org").status_code == 503
        assert request_link(c, "not-an-email").status_code == 503

        # after the cooldown one probe goes through; once delivery works again everything returns to normal
        monkeypatch.setattr(mailer, "send", original)
        mailer.HEALTH._last_failure -= mailer.DeliveryHealth.COOLDOWN + 1
        assert request_link(c, TO).status_code == 202
        assert mailer.HEALTH.available() and c.get("/api/auth/config").json()["email_available"] is True
        assert request_link(c, TO).status_code in (202,)  # per-email limit still answers the same generic 202


def test_passcode_mode_is_unaffected_by_the_breaker(tmp_path):
    for _ in range(mailer.DeliveryHealth.FAILURES):
        mailer.HEALTH.record(False)
    with build(tmp_path, auth_mode="passcode", auth_password="pw-pw-pw") as c:
        assert c.get("/api/auth/config").json() == {"auth_mode": "passcode", "email_available": True}


def test_breaker_state_is_json_safe_and_public_config_shape_is_fixed(tmp_path):
    with build(tmp_path) as c:
        body = c.get("/api/auth/config").json()
        assert set(body) == {"auth_mode", "email_available"} and json.dumps(body)
