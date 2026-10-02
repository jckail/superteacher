"""Outbound sign-in email. Three backends, no new dependency (httpx is already required by the AI SDK).

* ``sendgrid``: HTTPS call to the v3 mail API. Key from ``SENDGRID_API_KEY``, sender from ``AUTH_EMAIL_FROM``.
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
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Settings

log = logging.getLogger("superteacher.mailer")

SENDGRID_URL = "https://api.sendgrid.com/v3/mail/send"
SUBJECT = "Your Super Teacher sign-in link"


class MailerConfigError(RuntimeError):
    pass


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
    if backend == "file" and not settings.auth_email_outbox_dir:
        raise MailerConfigError("AUTH_EMAIL_BACKEND=file needs AUTH_EMAIL_OUTBOX_DIR.")


def send(settings: Settings, msg: Message, transport: httpx.BaseTransport | None = None) -> None:
    """Deliver one message synchronously. Raises on failure (callers catch and log)."""
    validate_settings(settings)
    backend = settings.auth_email_backend
    if backend == "console":
        log.warning("sign-in email generated (console backend; recipient and link redacted)")
    elif backend == "file":
        out = Path(settings.auth_email_outbox_dir or ".")
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{secrets.token_hex(8)}.json"
        path.write_text(json.dumps({"to": msg.to, "subject": msg.subject, "text": msg.text, "html": msg.html}))
        path.chmod(0o600)
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
            raise RuntimeError(f"sendgrid returned HTTP {r.status_code}")


def send_login_link(settings: Settings, to: str, link: str, transport: httpx.BaseTransport | None = None) -> bool:
    """Never raises; returns whether the provider accepted the message."""
    try:
        send(settings, build_login_message(to, link, settings.login_token_ttl_minutes), transport)
        return True
    except Exception as e:
        log.error("sign-in email failed: %s", type(e).__name__)  # type only: messages can echo addresses/keys
        return False


async def send_login_link_async(settings: Settings, to: str, link: str) -> bool:
    return await asyncio.to_thread(send_login_link, settings, to, link)
