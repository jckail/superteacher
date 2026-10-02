"""Enumeration resistance, rate limits, user cap, domain allowlist."""

import statistics
import time

from sqlalchemy import func, select

from superteacher.models import LoginToken, User
from tests.acct_util import build, outbox, request_link, sign_in


def test_identical_bodies_and_status_for_known_unknown_and_dropped(tmp_path):
    with build(tmp_path, accounts_max_users=1, accounts_email_allowlist_domains="example.com") as c:
        sign_in(c, tmp_path, "known@example.com")
        known = request_link(c, "known@example.com")
        unknown = request_link(c, "new@example.com")  # cap reached: dropped
        wrong_domain = request_link(c, "x@other.org")  # not allowed: dropped
        shapes = {(r.status_code, r.text) for r in (known, unknown, wrong_domain)}
        assert len(shapes) == 1, shapes
        assert known.status_code == 202


def test_dropped_requests_send_nothing(tmp_path):
    with build(tmp_path, accounts_max_users=1, accounts_email_allowlist_domains="example.com") as c:
        sign_in(c, tmp_path, "known@example.com")
        n = len(outbox(tmp_path))
        request_link(c, "new@example.com")
        request_link(c, "x@other.org")
        assert len(outbox(tmp_path)) == n
        request_link(c, "known@example.com")  # existing users can still sign in when the app is full
        assert len(outbox(tmp_path)) == n + 1


def test_user_cap_blocks_new_signups_only(tmp_path):
    with build(tmp_path, accounts_max_users=2) as c:
        sign_in(c, tmp_path, "a@example.com")
        sign_in(c, tmp_path, "b@example.com")
        request_link(c, "c@example.com")
        assert len(outbox(tmp_path)) == 2
        with c.app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(User)) == 2


def test_cap_is_rechecked_at_verification(tmp_path):
    """A link minted before the cap filled must not create user #N+1."""
    from tests.acct_util import token_from, verify

    with build(tmp_path, accounts_max_users=1) as c:
        request_link(c, "late@example.com")
        link = token_from(outbox(tmp_path)[-1])
        sign_in(c, tmp_path, "first@example.com")
        c.cookies.clear()
        assert verify(c, link).status_code == 400


def test_domain_allowlist(tmp_path):
    with build(tmp_path, accounts_email_allowlist_domains="school.org, @District.edu") as c:
        for email in ("a@school.org", "b@district.edu"):
            request_link(c, email)
        for email in ("c@gmail.com", "d@school.org.evil.com", "e@sub.school.org"):
            request_link(c, email)
        assert [m["to"] for m in outbox(tmp_path)] == ["a@school.org", "b@district.edu"]


def test_per_email_limit_is_silent_and_generic(tmp_path):
    with build(tmp_path, accounts_link_per_email_hour=3) as c:
        responses = [request_link(c, "a@example.com") for _ in range(6)]
        assert {(r.status_code, r.text) for r in responses} == {(202, responses[0].text)}
        assert len(outbox(tmp_path)) == 3
        request_link(c, "A@EXAMPLE.COM")  # same address after normalisation
        assert len(outbox(tmp_path)) == 3
        request_link(c, "other@example.com")  # other addresses are unaffected
        assert len(outbox(tmp_path)) == 4


def test_per_ip_limit_returns_429_with_retry_after(tmp_path):
    with build(tmp_path, accounts_link_per_ip_hour=3) as c:
        codes = [request_link(c, f"u{i}@example.com").status_code for i in range(5)]
        assert codes == [202, 202, 202, 429, 429]
        r = request_link(c, "u9@example.com")
        assert int(r.headers["retry-after"]) > 0
        assert "u9" not in r.text


def test_per_ip_limit_applies_to_invalid_emails_too(tmp_path):
    with build(tmp_path, accounts_link_per_ip_hour=2) as c:
        assert request_link(c, "nope").status_code == 422
        assert request_link(c, "nope2").status_code == 422
        assert request_link(c, "a@example.com").status_code == 429


def test_global_limit(tmp_path):
    with build(tmp_path, accounts_link_global_hour=2) as c:
        assert [request_link(c, f"u{i}@example.com").status_code for i in range(3)] == [202, 202, 429]


def test_proxy_headers_are_honoured_only_via_the_trusted_proxy_layer(tmp_path):
    """The limiter keys on request.client, which uvicorn rewrites from X-Forwarded-For only for trusted proxies."""
    from tests.sec_util import behind_proxy

    with build(tmp_path, accounts_link_per_ip_hour=1) as c:
        untrusted = behind_proxy(c, trusted=False)
        assert request_link(untrusted, "a@example.com", **{"X-Forwarded-For": "1.1.1.1"}).status_code == 202
        assert request_link(untrusted, "b@example.com", **{"X-Forwarded-For": "2.2.2.2"}).status_code == 429
    with build(tmp_path / "t", accounts_link_per_ip_hour=1) as c:
        trusted = behind_proxy(c, trusted=True)
        assert request_link(trusted, "a@example.com", **{"X-Forwarded-For": "1.1.1.1"}).status_code == 202
        assert request_link(trusted, "b@example.com", **{"X-Forwarded-For": "2.2.2.2"}).status_code == 202
        assert request_link(trusted, "c@example.com", **{"X-Forwarded-For": "1.1.1.1"}).status_code == 429


def test_invalid_email_shapes_are_rejected_without_sending(tmp_path):
    with build(tmp_path) as c:
        for bad in ("", "x", "a@b", "a b@c.co", "a@b.co\r\nBcc: v@x.co", "x" * 400):
            assert request_link(c, bad).status_code == 422, bad
        assert c.post("/api/auth/request-link", json={}, headers={"X-Requested-With": "t"}).status_code == 422
        assert outbox(tmp_path) == []


def test_no_token_rows_for_dropped_requests(tmp_path):
    with build(tmp_path, accounts_email_allowlist_domains="example.com") as c:
        request_link(c, "x@other.org")
        with c.app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(LoginToken)) == 0


def test_response_timing_does_not_separate_known_unknown_and_dropped(tmp_path):
    """Sanity check, not a proof: medians stay within a generous factor of each other."""
    with build(tmp_path, accounts_email_allowlist_domains="example.com", accounts_link_per_email_hour=1000) as c:
        sign_in(c, tmp_path, "known@example.com")

        def median(make_email, n=25):
            samples = []
            for i in range(n):
                t = time.perf_counter()
                request_link(c, make_email(i))
                samples.append(time.perf_counter() - t)
            return statistics.median(samples)

        known = median(lambda i: "known@example.com")
        unknown = median(lambda i: f"new{i}@example.com")
        dropped = median(lambda i: f"x{i}@other.org")  # no email is sent on this path
        slowest, fastest = max(known, unknown, dropped), min(known, unknown, dropped)
        assert slowest / fastest < 5, (known, unknown, dropped)


def test_metrics_is_bearer_only_in_accounts_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "metrics-token-for-tests")
    with build(tmp_path) as c:
        sign_in(c, tmp_path, "a@example.com")
        assert c.get("/api/metrics").status_code == 401  # a signed-in user is not an operator
        ok = c.get("/api/metrics", headers={"Authorization": "Bearer metrics-token-for-tests"})
        assert ok.status_code == 200
