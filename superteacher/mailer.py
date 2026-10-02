"""Outbound sign-in email. Four backends, no new dependency (httpx is already required by the AI SDK).

* ``sendgrid``: HTTPS call to the v3 mail API. Key from ``SENDGRID_API_KEY``, sender from ``AUTH_EMAIL_FROM``.
* ``smtp``: SMTP with mandatory verified TLS (STARTTLS or SSL), using ``SMTP_HOST`` and ``AUTH_EMAIL_FROM``.
* ``console``: logs a REDACTED notice only (never the link or the address). For local development.
* ``file``: writes the full message (including the link) to ``AUTH_EMAIL_OUTBOX_DIR``. For tests and e2e only.

``console`` and ``file`` expose links, so they are refused when ``K_SERVICE`` is set (Cloud Run) unless
``AUTH_EMAIL_ALLOW_INSECURE_BACKEND=true``. Sending is blocking I/O: callers run it off the event loop
(``send_login_link_async``) and after the HTTP response is produced, so timing never reveals whether an address
is known.
Failures are logged without the address, the token or the provider response body.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import secrets
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

import httpx

from . import observability
from .config import Settings

log = logging.getLogger("superteacher.mailer")

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
SUBJECT = "Your Super Teacher sign-in link"


class MailerConfigError(RuntimeError):
    pass


@dataclass(eq=False)
class DeliveryReservation:
    health: DeliveryHealth
    generation: int
    queued_at: float
    probe: bool
    started: bool = False
    released: bool = False

    def start(self) -> bool:
        return self.health.start(self)

    def finish(self, ok: bool) -> None:
        self.health.finish(self, ok)

    def release(self) -> None:
        self.health.release(self)


class DeliveryHealth:
    """Circuit breaker over sign-in email delivery.

    Sending fails for reasons the user cannot see (provider out of credits, revoked key, SMTP outage), and the
    sign-in endpoint deliberately gives the same reply whatever happens to one address. So when the last
    ``FAILURES`` sends in a row failed, the endpoint should say so honestly (HTTP 503) instead of promising a link
    that is not coming. After ``COOLDOWN`` seconds one attempt is allowed through to find out if it has recovered.
    State is per process and says nothing about any address, so it cannot be used to enumerate users.
    """

    FAILURES = 3
    COOLDOWN = 300.0
    QUEUED_LEASE = 30.0

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._consecutive = 0
        self._last_failure = 0.0
        self._generation = 0
        self._probe: DeliveryReservation | None = None

    def _record(self, ok: bool) -> None:
        was_open = self._consecutive >= self.FAILURES
        if ok:
            self._consecutive = 0
            if was_open:
                self._generation += 1
        else:
            self._consecutive += 1
            self._last_failure = self._clock()
            if not was_open and self._consecutive >= self.FAILURES:
                self._generation += 1

    def record(self, ok: bool) -> None:
        with self._lock:
            self._record(ok)

    def _queued_expired(self, claim: DeliveryReservation) -> bool:
        return not claim.started and self._clock() - claim.queued_at >= self.QUEUED_LEASE

    def _expire_probe(self) -> None:
        if self._probe is not None and self._queued_expired(self._probe):
            self._probe.released = True
            self._probe = None

    def available(self) -> bool:
        """Nonreserving public read; an expired queued probe is eligible again."""
        with self._lock:
            if self._probe is not None and not self._queued_expired(self._probe):
                return False
            if self._consecutive < self.FAILURES:
                return True
            return self._clock() - self._last_failure >= self.COOLDOWN

    def acquire(self) -> DeliveryReservation | None:
        with self._lock:
            self._expire_probe()
            if self._probe is not None:
                return None
            probe = self._consecutive >= self.FAILURES
            if probe and self._clock() - self._last_failure < self.COOLDOWN:
                return None
            claim = DeliveryReservation(self, self._generation, self._clock(), probe)
            if probe:
                self._probe = claim
            return claim

    def start(self, claim: DeliveryReservation) -> bool:
        with self._lock:
            if claim.health is not self or claim.released or claim.started or claim.generation != self._generation:
                return False
            if claim.probe:
                if self._probe is not claim:
                    return False
                if self._queued_expired(claim):
                    claim.released = True
                    self._probe = None
                    return False
            elif self._probe is not None or self._consecutive >= self.FAILURES:
                return False
            claim.started = True
            return True

    def finish(self, claim: DeliveryReservation, ok: bool) -> None:
        with self._lock:
            if claim.health is not self or claim.released or not claim.started:
                return
            current = (
                self._probe is claim if claim.probe else (self._probe is None and claim.generation == self._generation)
            )
            if current:
                if claim.probe:
                    self._probe = None
                self._record(ok)
            claim.released = True

    def release(self, claim: DeliveryReservation) -> None:
        with self._lock:
            if claim.health is self:
                if self._probe is claim:
                    self._probe = None
                claim.released = True

    def reset(self) -> None:
        with self._lock:
            self._consecutive = 0
            self._last_failure = 0.0
            self._generation += 1
            self._probe = None


HEALTH = DeliveryHealth()


def email_available() -> bool:
    return HEALTH.available()


def provider_reason(response: httpx.Response) -> str:
    """A short, safe description of why a provider refused: its own error text, bounded. (Our log redaction also
    scrubs anything that looks like an address, key or token.)"""
    try:
        errors = response.json().get("errors") or []
        text = "; ".join(str(e.get("message", "")) for e in errors if isinstance(e, dict))
    except Exception:
        text = ""
    return text.strip()[:160]


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    html: str


def build_login_message(to: str, link: str, ttl_minutes: int) -> Message:
    text = (
        "Hello,\n\n"
        f"Use this link to sign in to Super Teacher. It works once and expires in {ttl_minutes} minutes:\n\n"
        f"{link}\n\n"
        "If you didn't request this email, ignore it: nothing happens unless the link is opened.\n\n"
        "Super Teacher is a demo with synthetic data. Please don't enter real student information.\n"
    )
    safe = html.escape(link, quote=True)
    markup = (
        "<p>Hello,</p>"
        f"<p>Use this link to sign in to Super Teacher. It works once and expires in {ttl_minutes} minutes.</p>"
        f'<p><a href="{safe}">Sign in to Super Teacher</a></p>'
        f"<p>Or paste this address into your browser:<br>{safe}</p>"
        "<p>If you didn't request this email, ignore it: nothing happens unless the link is opened.</p>"
        "<p>Super Teacher is a demo with synthetic data. Please don't enter real student information.</p>"
    )
    return Message(to=to, subject=SUBJECT, text=text, html=markup)


def is_production() -> bool:
    return bool(os.environ.get("K_SERVICE"))


def validate_settings(settings: Settings) -> None:
    """Fail fast at startup (accounts mode) instead of on the first user's sign-in."""
    backend = settings.auth_email_backend
    if backend in ("console", "file") and is_production() and not settings.auth_email_allow_insecure_backend:
        raise MailerConfigError(
            f"AUTH_EMAIL_BACKEND={backend} exposes sign-in links and is refused in production (K_SERVICE is set). "
            "Use sendgrid, or set AUTH_EMAIL_ALLOW_INSECURE_BACKEND=true if you really mean it."
        )
    if backend == "sendgrid" and not (settings.sendgrid_api_key and settings.auth_email_from):
        raise MailerConfigError("AUTH_EMAIL_BACKEND=sendgrid needs SENDGRID_API_KEY and AUTH_EMAIL_FROM.")
    if backend == "smtp" and not (settings.smtp_host and settings.auth_email_from):
        raise MailerConfigError("AUTH_EMAIL_BACKEND=smtp needs SMTP_HOST and AUTH_EMAIL_FROM.")
    if backend == "file" and not settings.auth_email_outbox_dir:
        raise MailerConfigError("AUTH_EMAIL_BACKEND=file needs AUTH_EMAIL_OUTBOX_DIR.")


def _send_smtp(settings: Settings, msg: Message) -> None:
    email = EmailMessage()
    email["From"], email["To"], email["Subject"] = settings.auth_email_from, msg.to, msg.subject
    email.set_content(msg.text)
    email.add_alternative(msg.html, subtype="html")
    context = ssl.create_default_context()  # verifies the server certificate and hostname
    host, port = str(settings.smtp_host), settings.smtp_port
    if settings.smtp_security == "ssl":
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    with client:
        if settings.smtp_security == "starttls":
            client.starttls(context=context)
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(email)


def send(settings: Settings, msg: Message, transport: httpx.BaseTransport | None = None) -> None:
    """Deliver one message synchronously. Raises on failure (callers catch and log)."""
    validate_settings(settings)
    backend = settings.auth_email_backend
    if backend == "console":
        log.warning("sign-in email generated (console backend; recipient and link redacted)")
    elif backend == "file":
        out = Path(settings.auth_email_outbox_dir or ".")
        out.mkdir(parents=True, exist_ok=True)
        # Time-ordered names (then a random suffix) so "the newest message" is well defined for tests/e2e.
        path = out / f"{time.time_ns():020d}-{secrets.token_hex(4)}.json"
        # Create with private permissions: chmod after writing exposes the token
        # briefly when the process has a permissive umask.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump({"to": msg.to, "subject": msg.subject, "text": msg.text, "html": msg.html}, stream)
    elif backend == "smtp":
        _send_smtp(settings, msg)
    else:
        payload = {
            "personalizations": [{"to": [{"email": msg.to}]}],
            "from": {"email": settings.auth_email_from},
            "subject": msg.subject,
            "content": [{"type": "text/plain", "value": msg.text}, {"type": "text/html", "value": msg.html}],
            # No open/click tracking: the link must reach the user untouched, and nothing is measured.
            "tracking_settings": {
                "click_tracking": {"enable": False, "enable_text": False},
                "open_tracking": {"enable": False},
                "subscription_tracking": {"enable": False},
            },
        }
        with httpx.Client(timeout=10.0, transport=transport) as client:
            r = client.post(
                SENDGRID_URL, json=payload, headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"}
            )
        if r.status_code >= 300:
            reason = provider_reason(r)
            raise RuntimeError(f"sendgrid returned HTTP {r.status_code}" + (f": {reason}" if reason else ""))


def send_login_link(
    settings: Settings,
    to: str,
    link: str,
    transport: httpx.BaseTransport | None = None,
    *,
    reservation: DeliveryReservation | None = None,
) -> bool:
    """Never raises; returns whether the provider accepted the message."""
    claim = reservation if reservation is not None else HEALTH.acquire()
    if claim is None or not claim.start():
        return False
    try:
        send(settings, build_login_message(to, link, settings.login_token_ttl_minutes), transport)
        claim.finish(True)
        return True
    except Exception as e:
        # SMTP reached RCPT and refused this recipient: transport/auth are working.
        # Keep returning false, without making unrelated recipients unavailable.
        claim.finish(isinstance(e, smtplib.SMTPRecipientsRefused))
        # The exception type always; the provider's own (bounded, redacted) reason when we have one, because
        # "401" alone sent us looking at the wrong thing: the real cause was "Maximum credits exceeded".
        detail = ""
        if isinstance(e, RuntimeError):
            # Scrub here, not only in the log formatter: a provider can echo the key or the recipient in its message.
            secrets_in_play = (settings.sendgrid_api_key or "", settings.smtp_password or "", to)
            detail = observability.redact(str(e), tuple(x for x in secrets_in_play if x))
        log.error("sign-in email failed: %s%s", type(e).__name__, f" ({detail[:200]})" if detail else "")
        return False
    finally:
        claim.release()


async def send_login_link_async(settings: Settings, to: str, link: str) -> bool:
    return await asyncio.to_thread(send_login_link, settings, to, link)
