"""SMTP backend, the delivery circuit breaker, and honest behaviour when sign-in email is down.

Background (a real incident): SendGrid answered "Maximum credits exceeded", the app kept replying "a link is on its
way", and in accounts mode nobody could sign in. Now: the provider's reason is logged, repeated failures open a
breaker, and the sign-in endpoint answers 503 instead of a promise it cannot keep.
"""

import asyncio
import json
import logging
import smtplib
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import ClassVar

import httpx
import pytest
from fastapi import BackgroundTasks, HTTPException, Request

from superteacher import accounts, auth, mailer
from superteacher.config import Settings
from superteacher.models import LoginToken
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


def half_open(monkeypatch):
    clock = Clock()
    health = mailer.DeliveryHealth(clock)
    for _ in range(health.FAILURES):
        health.record(False)
    clock.t += health.COOLDOWN
    monkeypatch.setattr(mailer, "HEALTH", health)
    return health, clock


def test_half_open_acquisition_is_atomic_and_config_reads_do_not_claim(monkeypatch):
    health, _ = half_open(monkeypatch)
    assert all(mailer.email_available() for _ in range(10))
    barrier = threading.Barrier(8)

    def acquire():
        barrier.wait(timeout=5)
        return health.acquire()

    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: acquire(), range(8)))
    (claim,) = [reservation for reservation in reservations if reservation is not None]
    assert not health.available()
    claim.release()
    assert health.available() and health._consecutive == health.FAILURES


@pytest.mark.parametrize("replace_first", [False, True])
def test_expired_queued_sender_refuses_without_delivery_or_health_changes(monkeypatch, replace_first):
    health, clock = half_open(monkeypatch)
    old = health.acquire()
    assert old is not None
    clock.t += health.QUEUED_LEASE + 1
    assert health.available()
    replacement = health.acquire() if replace_first else None
    seen = []
    monkeypatch.setattr(mailer, "send", lambda *args: seen.append(args))
    failures = health._consecutive
    assert not mailer.send_login_link(smtp_settings(), TO, LINK, reservation=old)
    old.finish(True)
    old.release()
    assert seen == [] and health._consecutive == failures
    if replacement is None:
        replacement = health.acquire()
    assert replacement is not None and not health.available()
    replacement.release()


def test_started_probe_never_expires_and_closes_on_real_completion(monkeypatch):
    health, clock = half_open(monkeypatch)
    claim = health.acquire()
    assert claim is not None and claim.start()
    clock.t += health.QUEUED_LEASE + health.COOLDOWN + 1
    assert not health.available() and health.acquire() is None
    claim.finish(True)
    assert health.available() and health._consecutive == 0
    first, second = health.acquire(), health.acquire()
    assert first is not None and second is not None
    first.release()
    second.release()


def test_sender_start_racing_with_expiration_replacement_cannot_start_both(monkeypatch):
    health, clock = half_open(monkeypatch)
    old = health.acquire()
    assert old is not None
    barrier = threading.Barrier(2)

    def start_old():
        barrier.wait(timeout=5)
        return old.start()

    def replace():
        barrier.wait(timeout=5)
        clock.t += health.QUEUED_LEASE + 1
        return health.acquire()

    with ThreadPoolExecutor(max_workers=2) as pool:
        started = pool.submit(start_old)
        replacement = pool.submit(replace)
        old_started, new = started.result(timeout=5), replacement.result(timeout=5)
    if old_started:
        assert new is None and health.acquire() is None
        old.finish(False)
        assert not health.available()
    else:
        assert new is not None and new.start()
        old.finish(True)
        old.release()
        assert health.acquire() is None
        new.finish(True)
        assert health.available()


def route_request(client):
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "http",
            "path": "/api/auth/request-link",
            "headers": [(b"x-requested-with", b"test"), (b"host", b"testserver")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "app": client.app,
        }
    )


def test_actual_route_retains_deferred_claim_and_background_releases(tmp_path, monkeypatch):
    with build(tmp_path) as client:
        health, _ = half_open(monkeypatch)
        request = route_request(client)
        tasks = BackgroundTasks()
        assert auth.request_link(auth.RequestLinkBody(email=TO), request, tasks) == auth.GENERIC_LINK_REPLY
        assert len(tasks.tasks) == 1
        assert auth.auth_config(request) == {"auth_mode": "accounts", "email_available": False}
        with pytest.raises(HTTPException) as denied:
            auth.request_link(auth.RequestLinkBody(email="other@example.org"), request, BackgroundTasks())
        assert denied.value.status_code == 503
        asyncio.run(tasks())
        assert health.available() and health._consecutive == 0
        assert len(list((tmp_path / "outbox").glob("*.json"))) == 1


def test_actual_abandoned_route_task_cannot_send_or_clear_replacement(tmp_path, monkeypatch):
    with build(tmp_path) as client:
        health, clock = half_open(monkeypatch)
        request = route_request(client)
        abandoned, replacement = BackgroundTasks(), BackgroundTasks()
        assert auth.request_link(auth.RequestLinkBody(email=TO), request, abandoned) == auth.GENERIC_LINK_REPLY
        clock.t += health.QUEUED_LEASE + 1
        assert auth.auth_config(request)["email_available"] is True
        assert (
            auth.request_link(auth.RequestLinkBody(email="replacement@example.org"), request, replacement)
            == auth.GENERIC_LINK_REPLY
        )
        asyncio.run(abandoned())
        assert not health.available() and health._consecutive == health.FAILURES
        assert not list((tmp_path / "outbox").glob("*.json"))
        asyncio.run(replacement())
        assert health.available() and health._consecutive == 0
        (path,) = (tmp_path / "outbox").glob("*.json")
        assert json.loads(path.read_text())["to"] == "replacement@example.org"


def test_session_exit_failure_releases_before_scheduling_and_preserves_commit(tmp_path, monkeypatch):
    with build(tmp_path) as client:
        health, _ = half_open(monkeypatch)
        original_factory = client.app.state.session_factory
        with original_factory() as db:
            before_tokens = db.query(LoginToken).count()

        @contextmanager
        def failing_exit():
            with original_factory() as db:
                yield db
            raise RuntimeError("synthetic session exit failure")

        monkeypatch.setattr(client.app.state, "session_factory", failing_exit)
        tasks = BackgroundTasks()
        with pytest.raises(RuntimeError, match="synthetic session exit failure"):
            auth.request_link(auth.RequestLinkBody(email=TO), route_request(client), tasks)
        assert tasks.tasks == [] and health.available() and health._consecutive == health.FAILURES
        claim = health.acquire()
        assert claim is not None
        claim.release()
        assert not list((tmp_path / "outbox").glob("*.json"))
        with original_factory() as db:
            assert db.query(LoginToken).count() == before_tokens + 1


@pytest.mark.parametrize(
    "reason",
    [
        "quota",
        "invalid",
        "domain",
        "email_cap",
        "user_cap",
        "db_error",
        "token_error",
        "commit_error",
        "schedule_error",
    ],
)
def test_actual_route_no_send_exits_release_without_marking_provider_healthy(tmp_path, monkeypatch, reason):
    options = {"accounts_email_allowlist_domains": "school.org"} if reason == "domain" else {}
    with build(tmp_path, **options) as client:
        health, _ = half_open(monkeypatch)
        with client.app.state.session_factory() as db:
            before_tokens = db.query(LoginToken).count()
        if reason == "quota":
            monkeypatch.setattr(client.app.state.auth.link_ip, "allow", lambda _: False)
        elif reason == "email_cap":
            monkeypatch.setattr(accounts, "recent_token_count", lambda *args: 10_000)
        elif reason == "user_cap":
            monkeypatch.setattr(accounts, "count_users", lambda *args: 10_000)
        elif reason in {"db_error", "token_error", "commit_error", "schedule_error"}:

            def fail(*args, **kwargs):
                raise RuntimeError("synthetic failure")

            if reason == "db_error":
                monkeypatch.setattr(accounts, "reserve_link_request", fail)
            elif reason == "token_error":
                monkeypatch.setattr(accounts, "issue_login_token", fail)
            elif reason == "commit_error":
                monkeypatch.setattr(client.app.state.session_factory.class_, "commit", fail)
            else:
                monkeypatch.setattr(BackgroundTasks, "add_task", fail)
        if reason in {"db_error", "token_error", "commit_error", "schedule_error"}:
            with pytest.raises(RuntimeError, match="synthetic failure"):
                request_link(client, TO)
        else:
            response = request_link(client, "not-an-email" if reason == "invalid" else TO)
            expected = {"quota": 429, "invalid": 422}.get(reason, 202)
            assert response.status_code == expected
            if expected == 202:
                assert response.json() == auth.GENERIC_LINK_REPLY
        assert health.available() and health._consecutive == health.FAILURES
        claim = health.acquire()
        assert claim is not None
        claim.release()
        assert not list((tmp_path / "outbox").glob("*.json"))
        if reason != "schedule_error":
            with client.app.state.session_factory() as db:
                assert db.query(LoginToken).count() == before_tokens


def test_running_sender_is_exclusive_after_queued_lease_elapsed(monkeypatch):
    health, clock = half_open(monkeypatch)
    seen = []

    def deliver(*args):
        clock.t += health.QUEUED_LEASE + health.COOLDOWN
        assert health.acquire() is None and not mailer.email_available()
        assert mailer.send_login_link(smtp_settings(), "other@example.org", LINK) is False
        seen.append(True)

    monkeypatch.setattr(mailer, "send", deliver)
    assert mailer.send_login_link(smtp_settings(), TO, LINK)
    assert seen == [True] and health.available()


def test_duplicate_sender_cannot_release_an_already_started_probe(monkeypatch):
    health, _ = half_open(monkeypatch)
    claim = health.acquire()
    assert claim is not None and claim.start()
    seen = []
    monkeypatch.setattr(mailer, "send", lambda *args: seen.append(args))
    assert not mailer.send_login_link(smtp_settings(), TO, LINK, reservation=claim)
    assert seen == [] and health.acquire() is None and not health.available()
    claim.finish(True)
    assert health.available()


def test_closed_state_queued_callback_and_old_result_cannot_bypass_new_probe(monkeypatch):
    clock = Clock()
    health = mailer.DeliveryHealth(clock)
    monkeypatch.setattr(mailer, "HEALTH", health)
    queued, started = health.acquire(), health.acquire()
    assert queued is not None and started is not None and started.start()
    for _ in range(health.FAILURES):
        health.record(False)
    clock.t += health.COOLDOWN
    probe = health.acquire()
    assert probe is not None and probe.start()
    seen = []
    monkeypatch.setattr(mailer, "send", lambda *args: seen.append(args))
    assert not mailer.send_login_link(smtp_settings(), TO, LINK, reservation=queued)
    started.finish(True)
    queued.release()
    assert seen == [] and not health.available() and health._consecutive == health.FAILURES
    probe.finish(True)
    assert health.available()


def test_sender_releases_probe_even_on_escaping_exception(monkeypatch):
    health, _ = half_open(monkeypatch)
    claim = health.acquire()

    def interrupted(*args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(mailer, "send", interrupted)
    with pytest.raises(KeyboardInterrupt):
        mailer.send_login_link(smtp_settings(), TO, LINK, reservation=claim)
    assert health.available() and health._consecutive == health.FAILURES


@pytest.mark.parametrize("recovering", [False, True])
def test_recipient_refusal_does_not_lock_other_signins(fake_smtp, monkeypatch, caplog, recovering):
    if recovering:
        health, _ = half_open(monkeypatch)
    else:
        health = mailer.HEALTH

    def refuse(self, message):
        raise smtplib.SMTPRecipientsRefused({message["To"]: (550, b"secret-password SECRETTOKEN")})

    monkeypatch.setattr(FakeSMTP, "send_message", refuse)
    with caplog.at_level(logging.ERROR, logger="superteacher.mailer"):
        for _ in range(health.FAILURES + 1):
            assert mailer.send_login_link(smtp_settings(), TO, LINK) is False
            assert health.available() and health._consecutive == 0
    assert "SMTPRecipientsRefused" in caplog.text
    assert TO not in caplog.text and "secret-password" not in caplog.text and "SECRETTOKEN" not in caplog.text


def test_recipient_refusal_endpoint_stays_generic_and_auth_outage_still_opens(tmp_path, monkeypatch):
    with build(tmp_path) as client:

        def refuse(*args):
            raise smtplib.SMTPRecipientsRefused({TO: (550, b"rejected")})

        monkeypatch.setattr(mailer, "send", refuse)
        for _ in range(mailer.DeliveryHealth.FAILURES + 1):
            response = request_link(client, TO)
            assert response.status_code == 202 and response.json() == auth.GENERIC_LINK_REPLY
        assert mailer.email_available()

        def authentication_failure(*args):
            raise smtplib.SMTPAuthenticationError(535, b"secret-password")

        monkeypatch.setattr(mailer, "send", authentication_failure)
        for index in range(mailer.DeliveryHealth.FAILURES):
            assert request_link(client, f"outage{index}@example.com").status_code == 202
        assert request_link(client, "unrelated@example.org").status_code == 503
