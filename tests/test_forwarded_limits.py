"""Trusted-suffix auth identity under the real Uvicorn wildcard proxy middleware."""

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from superteacher.client_address import UNVERIFIED_CLIENT, rate_limit_client
from superteacher.config import Settings
from tests.acct_util import build as account_app
from tests.acct_util import request_link
from tests.sec_util import H, behind_proxy, build, login


def test_rotating_untrusted_prefix_cannot_reset_passcode_lockout():
    with build(auth_forwarded_for_trusted_hops=1) as app:
        client = behind_proxy(app, trusted=True)
        codes = [
            login(client, "wrong", **{"X-Forwarded-For": f"192.0.2.{i}, 198.51.100.7"}).status_code for i in range(1, 7)
        ]
        assert codes == [401, 401, 401, 401, 401, 429]
        assert login(client, **{"X-Forwarded-For": "192.0.2.200, 198.51.100.7"}).status_code == 429
        assert login(client, **{"X-Forwarded-For": "192.0.2.200, 198.51.100.8"}).status_code == 200


def test_two_verified_appended_hops_select_client_not_shared_proxy(tmp_path):
    with account_app(tmp_path, auth_forwarded_for_trusted_hops=2, accounts_link_per_ip_hour=1) as app:
        client = behind_proxy(app, trusted=True)
        assert (
            request_link(
                client, "a@example.com", **{"X-Forwarded-For": "192.0.2.1, 198.51.100.7, 203.0.113.10"}
            ).status_code
            == 202
        )
        assert (
            request_link(
                client, "b@example.com", **{"X-Forwarded-For": "192.0.2.2, 198.51.100.7, 203.0.113.10"}
            ).status_code
            == 429
        )
        assert (
            request_link(
                client, "c@example.com", **{"X-Forwarded-For": "192.0.2.2, 198.51.100.8, 203.0.113.10"}
            ).status_code
            == 202
        )


def test_rotating_untrusted_prefix_cannot_reset_token_verify_counter(tmp_path):
    with account_app(tmp_path, auth_forwarded_for_trusted_hops=1) as app:
        client = behind_proxy(app, trusted=True)
        codes = [
            client.post(
                "/api/auth/verify",
                json={"token": "x" * 32},
                headers={**H, "X-Forwarded-For": f"192.0.2.{i}, 198.51.100.7"},
            ).status_code
            for i in range(1, 32)
        ]
        assert codes == [400] * 30 + [429]


def connection(*values, host="192.0.2.9"):
    return Request(
        {"type": "http", "client": (host, 1234), "headers": [(b"x-forwarded-for", v.encode()) for v in values]}
    )


@pytest.mark.parametrize(
    "header,expected",
    [
        ("junk-prefix, 198.51.100.7", "198.51.100.7"),
        ("192.0.2.1, 2001:0DB8:0000::A", "2001:db8::a"),
        ("192.0.2.1, ::ffff:198.51.100.7", "198.51.100.7"),
    ],
)
def test_selected_address_is_canonical_and_prefix_is_not_trusted(header, expected):
    assert rate_limit_client(connection(header), trusted_hops=1) == expected


@pytest.mark.parametrize(
    "headers,hops",
    [
        ([], 1),
        ([""], 1),
        (["198.51.100.7,"], 1),
        (["198.51.100.7"], 2),
        (["198.51.100.7, not-an-ip"], 2),
        (["198.51.100.7", "203.0.113.9"], 1),
        (["192.0.2.1, 198.51.100.7:443"], 1),
        (["192.0.2.1, [2001:db8::1]"], 1),
        (["192.0.2.1, fe80::1%eth0"], 1),
        (["x" * 4097], 1),
    ],
)
def test_unqualified_header_uses_one_shared_bucket_not_attacker_controlled_request_client(headers, hops):
    assert rate_limit_client(connection(*headers, host="attacker-first"), trusted_hops=hops) == UNVERIFIED_CLIENT


def test_rotating_prefix_with_malformed_suffix_cannot_reset_passcode_counter():
    with build(auth_forwarded_for_trusted_hops=1) as app:
        client = behind_proxy(app, trusted=True)
        codes = [
            login(client, "wrong", **{"X-Forwarded-For": f"192.0.2.{i}, invalid-tail-{i}"}).status_code
            for i in range(1, 7)
        ]
        assert codes == [401] * 5 + [429]


def test_default_uses_request_client_without_trusting_raw_header():
    assert rate_limit_client(connection("198.51.100.7")) == "192.0.2.9"
    assert rate_limit_client(Request({"type": "http", "client": None, "headers": []})) == "unknown"


@pytest.mark.parametrize("hops", [-1, 9])
def test_hop_configuration_is_bounded(hops):
    with pytest.raises(ValidationError):
        Settings(auth_forwarded_for_trusted_hops=hops)
