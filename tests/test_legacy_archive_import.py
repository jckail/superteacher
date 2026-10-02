"""End-to-end offline import tests using exclusively invented captures."""

import copy
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import zipfile

import pytest

from superteacher import import_legacy_archive as importer


@pytest.fixture
def capture():
    classes = [{"id": "class-a", "name": " Mathematics "}]
    students = [
        {
            "id": f"student-{i}",
            "name": "Same Name",
            "class_id": "class-a",
            "section": "Blue",
            "grade": 7,
            "gpa": 3.2,
            "academic_performance": {"tests": {"Synthetic quiz": "82%"}, "homework": {}, "rank": "2"},
            "ai_insights": {"opaque": "synthetic content"},
            "future": {"nested": ["keep exactly"]},
        }
        for i in range(2)
    ]
    responses = []
    for path, payload in (
        ("/api/version", {"version": "synthetic", "git_commit": "synthetic"}),
        ("/api/db/classes", {"classes": classes}),
        ("/api/db/students", students),
        ("/api/db/classes/class-a/sections", {"sections": [{"class_id": "class-a", "name": "Blue"}]}),
        ("/api/db/classes", {"classes": classes}),
        ("/api/db/students", students),
    ):
        body = json.dumps(payload)
        responses.append(
            {
                "url": importer.PROVENANCE["source_base_url"] + path,
                "status": 200,
                "started_at": f"2026-10-02T00:00:{len(responses) * 2:02}Z",
                "completed_at": f"2026-10-02T00:00:{len(responses) * 2 + 1:02}Z",
                "body_utf8": body,
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "payload": copy.deepcopy(payload),
            }
        )
    return {
        **importer.PROVENANCE,
        "started_at": "2026-10-02T00:00:00Z",
        "completed_at": "2026-10-02T00:01:00Z",
        "consistency_limits": ["non-atomic"],
        "validation": dict.fromkeys(importer.VALIDATION_KEYS, True),
        "counts": {"classes": 1, "sections": 1, "students": 2, "responses": 6},
        "version_response": copy.deepcopy(responses[0]["payload"]),
        "responses": responses,
    }


def sync_bodies(capture):
    for response in capture["responses"]:
        response["body_utf8"] = json.dumps(response["payload"])
        response["body_sha256"] = hashlib.sha256(response["body_utf8"].encode()).hexdigest()


def run(tmp_path, capture, **kwargs):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    raw = json.dumps(capture, indent=2).encode()
    source.write_bytes(raw)
    source.chmod(0o400)
    destination = tmp_path / "bundle.zip"
    return importer.import_legacy_archive(
        source,
        destination,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        owner_id="rehearsal001",
        owner_email="rehearsal@example.invalid",
        **kwargs,
    )


def test_faithful_roster_and_standalone_bundle(tmp_path, capture):
    result = run(tmp_path, capture)
    assert result["counts"] == {"courses": 1, "sections": 1, "students": 2}
    destination = tmp_path / "bundle.zip"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with zipfile.ZipFile(destination) as bundle:
        assert set(bundle.namelist()) == {"native.db", "manifest.json", "original_archive.json"}
        assert bundle.read("original_archive.json") == (tmp_path / "source.json").read_bytes()
        for member in bundle.infolist():
            assert (member.external_attr >> 16) & 0o777 == 0o600
        manifest = json.loads(bundle.read("manifest.json"))
        assert len(set(manifest["id_maps"]["students"].values())) == 2
        assert manifest["normalization_changes"][0]["native"] == "Mathematics"
        assert all(
            row["fields"]["future"] == "retained_original_archive"
            for row in manifest["field_dispositions"]
            if row["kind"] == "student"
        )
        db = tmp_path / "verify.db"
        db.write_bytes(bundle.read("native.db"))
    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [("0003",)]
        assert connection.execute("SELECT id,disabled FROM users").fetchall() == [("rehearsal001", 1)]
        assert connection.execute("SELECT name,grade_level FROM students").fetchall() == [("Same Name", 7)] * 2
        assert connection.execute("SELECT DISTINCT owner_id FROM courses").fetchall() == [("rehearsal001",)]
        for table in importer.EMPTY_TABLES:
            assert connection.execute(f'SELECT count(*) FROM "{table}"').fetchone() == (0,)
    again = tmp_path / "again.zip"
    importer.import_legacy_archive(
        tmp_path / "source.json",
        again,
        expected_sha256=manifest["source_sha256"],
        owner_id="rehearsal001",
        owner_email="rehearsal@example.invalid",
    )
    with zipfile.ZipFile(again) as bundle:
        assert json.loads(bundle.read("manifest.json"))["id_maps"] == manifest["id_maps"]


@pytest.mark.parametrize(
    "problem",
    [
        "student-duplicate",
        "class-duplicate",
        "section-duplicate",
        "reference",
        "class-reference",
        "normalization",
        "grade-zero",
        "grade-bool",
        "grade-float",
        "name-control",
        "name-surrogate",
        "name-length",
        "name-blank",
        "repeat",
        "hash",
        "payload",
        "provenance",
        "count",
        "validation",
        "nonfinite",
    ],
)
def test_invalid_captures_fail_closed(tmp_path, capture, problem):
    first, repeat = capture["responses"][2]["payload"], capture["responses"][5]["payload"]
    if problem == "student-duplicate":
        first[1]["id"] = first[0]["id"]
    elif problem == "class-duplicate":
        capture["responses"][1]["payload"]["classes"] *= 2
        capture["counts"]["classes"] = 2
    elif problem == "section-duplicate":
        capture["responses"][3]["payload"]["sections"] *= 2
        capture["counts"]["sections"] = 2
    elif problem == "normalization":
        capture["responses"][3]["payload"]["sections"].append({"class_id": "class-a", "name": " Blue "})
        capture["counts"]["sections"] = 2
    elif problem in ("reference", "class-reference"):
        first[0]["section" if problem == "reference" else "class_id"] = "missing"
    elif problem.startswith("grade-"):
        first[0]["grade"] = {"grade-zero": 0, "grade-bool": True, "grade-float": 7.0}[problem]
    elif problem.startswith("name-"):
        first[0]["name"] = {
            "name-control": "secret\x00record",
            "name-surrogate": "\ud800",
            "name-length": "a" * 121,
            "name-blank": " ",
        }[problem]
    elif problem == "repeat":
        repeat[0]["name"] = "changed"
    elif problem == "provenance":
        capture["observed_revision"] = "unreviewed"
    elif problem == "count":
        capture["counts"]["students"] = 99
    elif problem == "validation":
        capture["validation"]["primary_shapes_valid"] = False
    elif problem == "nonfinite":
        first[0]["future"] = float("inf")
    if problem != "repeat":
        capture["responses"][5]["payload"] = copy.deepcopy(first)
        capture["responses"][4]["payload"] = copy.deepcopy(capture["responses"][1]["payload"])
    sync_bodies(capture)
    if problem == "hash":
        capture["responses"][2]["body_sha256"] = "0" * 64
    if problem == "payload":
        capture["responses"][2]["payload"] = []
    with pytest.raises(importer.LegacyImportError) as error:
        run(tmp_path, capture)
    assert "secret" not in str(error.value)
    assert not (tmp_path / "bundle.zip").exists()
    assert not list(tmp_path.glob(".legacy-import-*"))


@pytest.mark.parametrize(
    "problem",
    [
        "exists",
        "source-alias",
        "source-link",
        "destination-link",
        "writable",
        "permissive",
        "bad-hash",
        "bad-owner",
        "bad-email",
        "publication",
        "transaction",
    ],
)
def test_artifact_and_owner_safety(tmp_path, capture, monkeypatch, problem):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    raw = json.dumps(capture).encode()
    source.write_bytes(raw)
    source.chmod(0o400)
    destination = tmp_path / "bundle.zip"
    sha = hashlib.sha256(raw).hexdigest()
    owner, email = "rehearsal001", "rehearsal@example.invalid"
    if problem == "exists":
        destination.write_bytes(b"untouched")
    elif problem == "source-alias":
        destination = source
    elif problem == "source-link":
        link = tmp_path / "link.json"
        link.symlink_to(source)
        source = link
    elif problem == "destination-link":
        destination.symlink_to(source)
    elif problem == "writable":
        source.chmod(0o600)
    elif problem == "permissive":
        source.chmod(0o444)
    elif problem == "bad-hash":
        sha = "0" * 64
    elif problem == "bad-owner":
        owner = None
    elif problem == "bad-email":
        email = None
    elif problem == "publication":

        def fail(*args, **kwargs):
            raise OSError("private detail")

        monkeypatch.setattr(os, "link", fail)
    elif problem == "transaction":

        def fail(*args, **kwargs):
            raise RuntimeError("private detail")

        monkeypatch.setattr(importer.Session, "flush", fail)
    with pytest.raises(importer.LegacyImportError) as error:
        importer.import_legacy_archive(source, destination, expected_sha256=sha, owner_id=owner, owner_email=email)
    assert "private detail" not in str(error.value)
    assert source.read_bytes() == raw
    if problem == "exists":
        assert destination.read_bytes() == b"untouched"
    elif problem not in ("source-alias", "destination-link"):
        assert not destination.exists()
    assert not list(tmp_path.glob(".legacy-import-*"))


def test_native_case_insensitive_course_collision(tmp_path, capture):
    capture["responses"][1]["payload"]["classes"].append({"id": "class-b", "name": "MATHEMATICS"})
    capture["responses"][4]["payload"] = copy.deepcopy(capture["responses"][1]["payload"])
    section_response = copy.deepcopy(capture["responses"][3])
    section_response["url"] = importer.PROVENANCE["source_base_url"] + "/api/db/classes/class-b/sections"
    section_response["payload"] = {"sections": []}
    capture["responses"].insert(4, section_response)
    capture["counts"]["responses"] = 7
    for index, response in enumerate(capture["responses"]):
        response["started_at"] = f"2026-10-02T00:00:{index * 2:02}Z"
        response["completed_at"] = f"2026-10-02T00:00:{index * 2 + 1:02}Z"
    capture["counts"]["classes"] = 2
    sync_bodies(capture)
    with pytest.raises(importer.LegacyImportError):
        run(tmp_path, capture)
    assert not (tmp_path / "bundle.zip").exists()


@pytest.mark.parametrize("problem", ["hardlink", "private-dir", "source-change", "publish-race", "owner-collision"])
def test_remaining_filesystem_and_identity_boundaries(tmp_path, capture, monkeypatch, problem):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    raw = json.dumps(capture).encode()
    source.write_bytes(raw)
    source.chmod(0o400)
    destination = tmp_path / "bundle.zip"
    sha = hashlib.sha256(raw).hexdigest()
    owner_id = "rehearsal001"
    if problem == "hardlink":
        os.link(source, tmp_path / "alias.json")
    elif problem == "private-dir":
        tmp_path.chmod(0o755)
    elif problem == "source-change":
        real_database = importer._database

        def change(*args):
            real_database(*args)
            source.chmod(0o600)
            source.write_bytes(b"changed")
            source.chmod(0o400)

        monkeypatch.setattr(importer, "_database", change)
    elif problem == "publish-race":
        real_link = os.link

        def race(*args, **kwargs):
            destination.write_bytes(b"other owner")
            real_link(*args, **kwargs)

        monkeypatch.setattr(os, "link", race)
    elif problem == "owner-collision":
        # Compute the deterministic source class ID then demand a collision with owner.
        owner_id = hashlib.sha256(json.dumps([sha, "course", "class-a"], ensure_ascii=True).encode()).hexdigest()[:12]
    if problem == "owner-collision":
        # Owner IDs and roster IDs must be independent identities even across tables.
        with pytest.raises(importer.LegacyImportError):
            importer.import_legacy_archive(
                source, destination, expected_sha256=sha, owner_id=owner_id, owner_email="rehearsal@example.invalid"
            )
    else:
        with pytest.raises(importer.LegacyImportError):
            importer.import_legacy_archive(
                source, destination, expected_sha256=sha, owner_id=owner_id, owner_email="rehearsal@example.invalid"
            )
    if problem == "publish-race":
        assert destination.read_bytes() == b"other owner"
    else:
        assert not destination.exists()
    assert not list(tmp_path.glob(".legacy-import-*"))


@pytest.mark.parametrize(
    "replacement", [b'{"duplicate":1,"duplicate":2}', b'{"value":1e999}', b'{"value":NaN}', b'{"value":-Infinity}']
)
def test_nonstandard_json_rejected_without_publication(tmp_path, replacement):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    source.write_bytes(replacement)
    source.chmod(0o400)
    with pytest.raises(importer.LegacyImportError):
        importer.import_legacy_archive(
            source,
            tmp_path / "bundle.zip",
            expected_sha256=hashlib.sha256(replacement).hexdigest(),
            owner_id="rehearsal001",
            owner_email="rehearsal@example.invalid",
        )
    assert not (tmp_path / "bundle.zip").exists()


@pytest.mark.parametrize("stored", [True, 1.0])
def test_body_payload_type_drift_rejected(tmp_path, capture, stored):
    response = capture["responses"][0]
    response["body_utf8"] = '{"value":1}'
    response["body_sha256"] = hashlib.sha256(response["body_utf8"].encode()).hexdigest()
    response["payload"] = {"value": stored}
    with pytest.raises(importer.LegacyImportError):
        run(tmp_path, capture)
    assert not (tmp_path / "bundle.zip").exists()


def test_repeat_numeric_type_drift_rejected(tmp_path, capture):
    capture["responses"][5]["payload"][0]["grade"] = 7.0
    sync_bodies(capture)
    with pytest.raises(importer.LegacyImportError):
        run(tmp_path, capture)
    assert not (tmp_path / "bundle.zip").exists()


def test_unicode_section_normalization_collision(tmp_path, capture):
    capture["responses"][3]["payload"]["sections"].extend(
        [{"class_id": "class-a", "name": "e\u0301"}, {"class_id": "class-a", "name": "\u00e9"}]
    )
    capture["counts"]["sections"] = 3
    sync_bodies(capture)
    with pytest.raises(importer.LegacyImportError, match="uniqueness collision"):
        run(tmp_path, capture)
    assert not (tmp_path / "bundle.zip").exists()


@pytest.mark.parametrize("problem", ["version", "response-count", "missing-validation", "time"])
def test_capture_provenance_bindings(tmp_path, capture, problem):
    if problem == "version":
        capture["version_response"]["git_commit"] = "different"
    elif problem == "response-count":
        capture["counts"]["responses"] = 99
    elif problem == "missing-validation":
        capture["validation"].pop("primary_shapes_valid")
    else:
        capture["responses"][3]["completed_at"] = "2026-10-03T00:00:00Z"
    with pytest.raises(importer.LegacyImportError):
        run(tmp_path, capture)
    assert not (tmp_path / "bundle.zip").exists()


def test_unchanged_frozen_source_accepts_atime_update(tmp_path, capture):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    raw = json.dumps(capture).encode()
    source.write_bytes(raw)
    source.chmod(0o400)
    os.utime(source, ns=(1, source.stat().st_mtime_ns))
    before = source.stat()
    result = importer.import_legacy_archive(
        source,
        tmp_path / "bundle.zip",
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        owner_id="rehearsal001",
        owner_email="rehearsal@example.invalid",
    )
    after = source.stat()
    assert result["status"] == "imported"
    assert after.st_atime_ns > before.st_atime_ns
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_ctime_ns == before.st_ctime_ns
    assert after.st_size == before.st_size
    with zipfile.ZipFile(tmp_path / "bundle.zip") as bundle:
        assert bundle.read("original_archive.json") == raw
    assert source.read_bytes() == raw


def test_fifo_source_is_refused_without_waiting_for_writer(tmp_path):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.fifo"
    os.mkfifo(source, 0o400)
    destination = tmp_path / "bundle.zip"
    # A subprocess deadline prevents a regression to blocking FIFO open from
    # hanging the verification runner; the FIFO has deliberately no writer.
    script = """
import sys
from superteacher.import_legacy_archive import LegacyImportError, import_legacy_archive
try:
    import_legacy_archive(sys.argv[1], sys.argv[2], expected_sha256="0" * 64,
                          owner_id="rehearsal001", owner_email="rehearsal@example.invalid")
except LegacyImportError:
    print("refused")
else:
    raise SystemExit("unexpected publication")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(destination)],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    assert result.stdout.strip() == "refused"
    assert not destination.exists()
    assert not list(tmp_path.glob(".legacy-import-*"))


@pytest.mark.parametrize("mutation", ["content", "mode"])
def test_mutation_during_source_read_is_refused(tmp_path, capture, monkeypatch, mutation):
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    raw = json.dumps(capture).encode()
    source.write_bytes(raw)
    source.chmod(0o400)
    real_fstat = os.fstat
    calls = 0

    def changed_stat(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            source.chmod(0o600)
            if mutation == "content":
                source.write_bytes(raw + b" ")
                source.chmod(0o400)
        return real_fstat(fd)

    monkeypatch.setattr(os, "fstat", changed_stat)
    with pytest.raises(importer.LegacyImportError, match="Source changed while reading"):
        importer.import_legacy_archive(
            source,
            tmp_path / "bundle.zip",
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            owner_id="rehearsal001",
            owner_email="rehearsal@example.invalid",
        )
    assert not (tmp_path / "bundle.zip").exists()
    assert not list(tmp_path.glob(".legacy-import-*"))
