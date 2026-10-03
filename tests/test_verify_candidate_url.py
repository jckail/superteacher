from pathlib import Path

import pytest

from scripts import verify_candidate

BASE = "https://superteacher-overhaul-staging-vbufkr2qma-uc.a.run.app"
TAGGED = "https://local-a98975a---superteacher-overhaul-staging-vbufkr2qma-uc.a.run.app"


def test_existing_isolated_service_url_remains_supported():
    assert verify_candidate.candidate_url(BASE + "/") == BASE


def test_exact_tag_requires_explicit_selection():
    assert verify_candidate.candidate_url(TAGGED, expected_tag="local-a98975a") == TAGGED
    with pytest.raises(ValueError):
        verify_candidate.candidate_url(TAGGED)


@pytest.mark.parametrize("url", [BASE, TAGGED.replace("local-a98975a", "other-tag")])
def test_selected_tag_refuses_old_serving_route_and_other_tags(url):
    with pytest.raises(ValueError):
        verify_candidate.candidate_url(url, expected_tag="local-a98975a")


@pytest.mark.parametrize("tag", ["", "UPPER", "-first", "last-", "a" * 64, "bad.tag", "x---y", "x/y"])
def test_invalid_tag_fails_closed(tag):
    with pytest.raises(ValueError):
        verify_candidate.candidate_url(TAGGED, expected_tag=tag)


@pytest.mark.parametrize(
    "url",
    [
        TAGGED.replace("https:", "http:"),
        TAGGED + ":444",
        TAGGED + "/api/ready",
        TAGGED + "?redirect=1",
        TAGGED + "#fragment",
        TAGGED.replace("https://", "https://user:password@"),
        TAGGED + ".evil.example",
        TAGGED.replace("superteacher-overhaul-staging", "superteacher"),
        "https://local-a98975a---localhost",
        "https://127.0.0.1",
    ],
)
def test_tag_does_not_broaden_transport_or_service_boundary(url):
    with pytest.raises(ValueError):
        verify_candidate.candidate_url(url, expected_tag="local-a98975a")


def test_cli_rejects_old_route_before_credentials_receipt_or_network(monkeypatch, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected URL reached credentials or network")

    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(verify_candidate, "private_json", forbidden)
    monkeypatch.setattr(verify_candidate.httpx, "Client", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        [
            "verify_candidate.py",
            "--url",
            BASE,
            "--expected-tag",
            "local-a98975a",
            "--expected-version",
            "synthetic-source",
            "--credentials",
            str(Path("missing-credentials.json")),
            "--receipt",
            str(receipt),
            "--isolated-candidate",
        ],
    )
    assert verify_candidate.main() == 1
    assert not receipt.exists()
    assert "validate_inputs (ValueError)" in capsys.readouterr().err
