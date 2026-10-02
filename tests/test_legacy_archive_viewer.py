"""Offline viewer acceptance uses invented captures and private temporary files."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from tests.test_legacy_archive_import import capture as legacy_capture
from tests.test_legacy_archive_import import run


def frozen(path, value):
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    path.chmod(0o400)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def capture():
    return legacy_capture.__wrapped__()


@pytest.fixture
def approved(tmp_path, capture):
    import zipfile

    from superteacher import import_legacy_archive as importer

    run(tmp_path, capture)
    bundle = tmp_path / "bundle.zip"
    bundle.chmod(0o400)
    with zipfile.ZipFile(bundle) as z:
        manifest = json.loads(z.read("manifest.json"))
    sid = "student-0"
    now = datetime.now(UTC)
    grant = {
        "version": 1,
        "authorization_reference": "synthetic-approval",
        "actor": "synthetic-operator",
        "operator_uid": os.getuid(),
        "recipient_reference": "synthetic-private-review",
        "approved_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "bundle_sha256": hashlib.sha256(bundle.read_bytes()).hexdigest(),
        "source_sha256": manifest["source_sha256"],
        "importer_version": importer.IMPORTER_VERSION,
        "importer_sha256": manifest["importer_sha256"],
        "native_revision": "0003",
        "owner_id": manifest["owner"]["id"],
        "native_student_id": manifest["id_maps"]["students"][sid],
        "source_student_id": sid,
        "source_class_id": "class-a",
        "source_section": "Blue",
        "aggregates": ["gpa"],
        "purpose": "operator_history_review",
        "identity_disposition": "verified_archive_review",
        "retention_delivery_reference": "synthetic-retention-no-delivery",
    }
    receipt = tmp_path / "receipt.json"
    receipt_hash = frozen(receipt, grant)
    request = {
        "version": 1,
        "bundle_path": str(bundle),
        "receipt_path": str(receipt),
        "output_path": str(tmp_path / "history.txt"),
        "audit_path": str(tmp_path / "audit.jsonl"),
        "owner_id": grant["owner_id"],
        "source_student_id": sid,
        "aggregates": ["gpa"],
    }
    request_path = tmp_path / "request.json"
    frozen(request_path, request)
    return request_path, request, grant, grant["bundle_sha256"], receipt_hash


def test_selected_history_private_and_unchanged(approved):
    from superteacher.view_legacy_archive import view_legacy_archive

    path, request, _, bundle_hash, receipt_hash = approved
    assert view_legacy_archive(path, expected_bundle_sha256=bundle_hash, expected_receipt_sha256=receipt_hash) == {
        "status": "created",
        "students": 1,
    }
    from pathlib import Path

    output = Path(request["output_path"])
    text = output.read_text()
    assert "Synthetic quiz" in text and "82%" in text
    assert "retained historical percentage string" in text
    assert "gpa: 3.2" in text
    assert "opaque" not in text and "future" not in text
    assert "Dates and raw points/denominators are unavailable" in text
    assert output.stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(Path(request["bundle_path"]).read_bytes()).hexdigest() == bundle_hash


def invoke(approved, **overrides):
    from superteacher.view_legacy_archive import view_legacy_archive

    path, _, _, bundle_hash, receipt_hash = approved
    return view_legacy_archive(
        path,
        expected_bundle_sha256=overrides.get("bundle", bundle_hash),
        expected_receipt_sha256=overrides.get("receipt", receipt_hash),
    )


def reset_request(approved):
    path, request, grant, bundle_hash, _ = approved
    from pathlib import Path

    receipt_hash = frozen(Path(request["receipt_path"]), grant)
    frozen(path, request)
    return path, request, grant, bundle_hash, receipt_hash


@pytest.mark.parametrize(
    "change", ["owner", "student", "expired", "uid", "purpose", "disposition", "aggregate", "importer"]
)
def test_bad_grants_refuse_without_outputs(approved, change):
    from pathlib import Path

    from superteacher.view_legacy_archive import ViewerError

    _, request, grant, _, _ = approved
    if change == "owner":
        request["owner_id"] = "foreign-owner"
    elif change == "student":
        request["source_student_id"] = "student-1"
    elif change == "expired":
        grant["expires_at"] = "2000-01-01T00:00:00Z"
    elif change == "uid":
        grant["operator_uid"] += 1
    elif change == "purpose":
        grant["purpose"] = "teacher-download"
    elif change == "disposition":
        grant["identity_disposition"] = "deleted"
    elif change == "aggregate":
        request["aggregates"] = ["attendance_days"]
    else:
        grant["importer_sha256"] = "0" * 64
    with pytest.raises(ViewerError):
        invoke(reset_request(approved))
    assert not Path(request["output_path"]).exists() and not Path(request["audit_path"]).exists()


@pytest.mark.parametrize("pin", ["bundle", "receipt"])
def test_external_digest_pins_required(approved, pin):
    from superteacher.view_legacy_archive import ViewerError

    with pytest.raises(ViewerError, match="digest mismatch"):
        invoke(approved, **{pin: "0" * 64})


def test_exact_native_selector_and_same_name_identity(approved):
    from pathlib import Path

    _, request, grant, _, _ = approved
    del request["source_student_id"]
    request["native_student_id"] = grant["native_student_id"]
    invoke(reset_request(approved))
    text = Path(request["output_path"]).read_text()
    assert "Source identity: student-0" in text and "student-1" not in text
    entries = [json.loads(line) for line in Path(request["audit_path"]).read_text().splitlines()]
    assert entries[0]["status"] == "pending_publication"
    assert entries[1]["status"] == "published_locally_not_delivered"
    assert Path(request["audit_path"]).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "kind", ["symlink", "hardlink", "fifo", "permissions", "parent", "both_selectors", "unknown_key"]
)
def test_unsafe_request_refuses(approved, kind):
    from pathlib import Path

    from superteacher.view_legacy_archive import ViewerError

    path, request, grant, _, _ = approved
    if kind == "both_selectors":
        request["native_student_id"] = grant["native_student_id"]
        frozen(path, request)
    elif kind == "unknown_key":
        request["name"] = "Same Name"
        frozen(path, request)
    elif kind == "permissions":
        path.chmod(0o600)
    elif kind == "parent":
        path.parent.chmod(0o755)
    else:
        alias = Path(str(path) + ".alias")
        if kind == "hardlink":
            os.link(path, alias)
        elif kind == "symlink":
            alias.symlink_to(path)
            path = alias
        else:
            os.mkfifo(alias, mode=0o400)
            path = alias
    from superteacher.view_legacy_archive import view_legacy_archive

    with pytest.raises(ViewerError):
        view_legacy_archive(path, expected_bundle_sha256=approved[3], expected_receipt_sha256=approved[4])


def repack(approved, mutate):
    import io
    import stat
    import zipfile
    from pathlib import Path

    _, request, grant, _, _ = approved
    path = Path(request["bundle_path"])
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    mutate(parts)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, raw in parts.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            z.writestr(info, raw)
    bundle_hash = frozen(path, data.getvalue())
    grant["bundle_sha256"] = bundle_hash
    refreshed = reset_request(approved)
    return *refreshed[:3], bundle_hash, refreshed[4]


@pytest.mark.parametrize("change", ["map", "selection", "disposition", "body", "source", "extra_zip", "database"])
def test_internally_contradictory_bundle_refuses_even_when_repinned(approved, change):
    from superteacher.view_legacy_archive import ViewerError

    def mutate(parts):
        manifest = json.loads(parts["manifest.json"])
        if change == "map":
            manifest["id_maps"]["students"]["student-0"] = "000000000000"
        elif change == "selection":
            manifest["selected_response_indices"]["/api/db/students"] = [5]
        elif change == "disposition":
            manifest["field_dispositions"] = []
        elif change == "body":
            archive = json.loads(parts["original_archive.json"])
            archive["responses"][2]["body_utf8"] = "[]"
            parts["original_archive.json"] = json.dumps(archive).encode()
            # Pin source too; response body/payload/hash must still contradict.
            approved[2]["source_sha256"] = hashlib.sha256(parts["original_archive.json"]).hexdigest()
            manifest["source_sha256"] = approved[2]["source_sha256"]
        elif change == "source":
            parts["original_archive.json"] += b" "
        elif change == "extra_zip":
            parts["../secret"] = b"hostile"
        else:
            parts["native.db"] = b"not sqlite"
            manifest["native_db_sha256"] = hashlib.sha256(parts["native.db"]).hexdigest()
        parts["manifest.json"] = json.dumps(manifest).encode()

    with pytest.raises(ViewerError):
        invoke(repack(approved, mutate))


@pytest.mark.parametrize("shape", ["duplicate", "deep", "nonfinite", "utf16", "nodes"])
def test_json_guard_bounds_and_strictness(shape, monkeypatch):
    from superteacher import view_legacy_archive as viewer

    value = {
        "duplicate": b'{"a":1,"a":2}',
        "deep": b"[" * 70 + b"0" + b"]" * 70,
        "nonfinite": b"1e999",
        "utf16": "[]".encode("utf-16"),
        "nodes": b"[1,2,3]",
    }[shape]
    if shape == "nodes":
        monkeypatch.setattr(viewer, "MAX_NODES", 2)
    with pytest.raises((viewer.ViewerError, UnicodeDecodeError)):
        viewer._Budget().parse(value)


def test_controls_and_unsupported_history_and_output_bound(approved, monkeypatch):
    from superteacher import view_legacy_archive as viewer

    archive = {
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:01:00Z",
        "observed_revision": "synthetic",
        "version_response": {"version": "synthetic", "git_commit": "synthetic"},
        "schema_candidate_commit": "synthetic",
    }
    student = {
        "id": "student-0",
        "name": "Éva",
        "class_id": "class-a",
        "section": "Blue",
        "academic_performance": {"tests": {"quiz\n\u202e": "0%\t"}, "homework": {}},
    }
    output = viewer._render(archive, student, approved[2], []).decode()
    assert "quiz\\u000a\\u202e: 0%\\u0009" in output
    student["academic_performance"]["tests"]["quiz\n\u202e"] = 0
    with pytest.raises(viewer.ViewerError, match="history value"):
        viewer._render(archive, student, approved[2], [])
    student["academic_performance"]["tests"] = {}
    monkeypatch.setattr(viewer, "MAX_REPORT", 10)
    with pytest.raises(viewer.ViewerError, match="report limit"):
        viewer._render(archive, student, approved[2], [])


@pytest.mark.parametrize("existing", ["output_path", "audit_path"])
def test_no_overwrite(approved, existing):
    from pathlib import Path

    from superteacher.view_legacy_archive import ViewerError

    path = Path(approved[1][existing])
    path.write_bytes(b"existing-private-canary")
    path.chmod(0o600)
    with pytest.raises(ViewerError):
        invoke(approved)
    assert path.read_bytes() == b"existing-private-canary"


def test_publication_race_and_temp_cleanup(approved, monkeypatch):
    from pathlib import Path

    from superteacher import view_legacy_archive as viewer

    original = os.link
    output = Path(approved[1]["output_path"])

    def competing(src, dst, **kwargs):
        output.write_bytes(b"competitor")
        return original(src, dst, **kwargs)

    monkeypatch.setattr(viewer.os, "link", competing)
    with pytest.raises(viewer.ViewerError):
        invoke(approved)
    assert output.read_bytes() == b"competitor"
    assert "publication_failed" in Path(approved[1]["audit_path"]).read_text()
    assert not list(output.parent.glob(".legacy-*"))


def test_cli_logs_never_echo_private_arguments(approved, capsys):
    from superteacher.view_legacy_archive import main

    assert main(["--secret-private-selector", "STUDENT-CANARY"]) == 1
    assert "STUDENT-CANARY" not in capsys.readouterr().err
    assert (
        main(
            [
                "--request-file",
                str(approved[0]),
                "--expected-bundle-sha256",
                "0" * 64,
                "--expected-receipt-sha256",
                approved[4],
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    assert str(approved[0]) not in captured.err and "student-0" not in captured.err
    assert (
        main(
            [
                "--request-file",
                str(approved[0]),
                "--expected-bundle-sha256",
                approved[3],
                "--expected-receipt-sha256",
                approved[4],
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"status": "created", "students": 1}


@pytest.mark.parametrize("change", ["roster", "view", "trigger", "events"])
def test_database_evidence_is_readonly_and_structurally_checked(approved, change):
    import sqlite3
    from pathlib import Path

    from superteacher.view_legacy_archive import ViewerError

    def mutate(parts):
        path = Path(approved[1]["output_path"]).parent / "synthetic-mutant.db"
        path.write_bytes(parts["native.db"])
        path.chmod(0o600)
        with sqlite3.connect(path) as db:
            if change == "roster":
                db.execute("UPDATE students SET name='DATABASE-PRIVATE-CANARY'")
            elif change == "view":
                db.execute("CREATE VIEW unexpected AS SELECT name FROM students")
            elif change == "trigger":
                db.execute("CREATE TRIGGER unexpected AFTER INSERT ON notes BEGIN SELECT 1; END")
            else:
                db.execute("INSERT INTO ai_budget(day,count) VALUES('2026-01-01',1)")
        parts["native.db"] = path.read_bytes()
        manifest = json.loads(parts["manifest.json"])
        manifest["native_db_sha256"] = hashlib.sha256(parts["native.db"]).hexdigest()
        parts["manifest.json"] = json.dumps(manifest).encode()

    refreshed = repack(approved, mutate)
    with pytest.raises(ViewerError):
        invoke(refreshed)
    assert not list(Path(approved[1]["output_path"]).parent.glob(".legacy-view-*"))


@pytest.mark.parametrize("change", ["duplicate", "symlink", "oversized", "bad_crc"])
def test_zip_rejects_hostile_member_layouts(change, monkeypatch):
    import io
    import stat
    import warnings
    import zipfile

    from superteacher import view_legacy_archive as viewer

    stream = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(stream, "w") as z:
        warnings.simplefilter("ignore", UserWarning)
        for name in viewer.MEMBERS:
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            if change == "symlink" and name == "native.db":
                info.external_attr = (stat.S_IFLNK | 0o600) << 16
            z.writestr(info, b"synthetic")
        if change == "duplicate":
            z.writestr("native.db", b"duplicate")
    raw = stream.getvalue()
    if change == "oversized":
        monkeypatch.setitem(viewer.MEMBERS, "native.db", 2)
    elif change == "bad_crc":
        raw = raw.replace(b"synthetic", b"corrupted", 1)
    with pytest.raises((viewer.ViewerError, zipfile.BadZipFile)):
        viewer._bundle(raw)


def test_response_body_depth_guard_precedes_recursive_importer(monkeypatch):
    from superteacher import view_legacy_archive as viewer

    raw = json.dumps({"responses": [{"body_utf8": "[" * 70 + "0" + "]" * 70}]}).encode()
    parts = {"original_archive.json": raw, "manifest.json": b"{}"}

    def forbidden(*args):
        pytest.fail("recursive importer was invoked before nested body guard")

    monkeypatch.setattr(viewer.importer, "_parse", forbidden)
    with pytest.raises(viewer.ViewerError, match="structural limit"):
        viewer._evidence(
            parts, viewer._Budget(), {"source_sha256": hashlib.sha256(raw).hexdigest(), "owner_id": "rehearsal001"}
        )


def test_no_provider_calls_and_readonly_snapshot(approved, monkeypatch):
    import socket
    import sqlite3

    from superteacher import view_legacy_archive as viewer

    original = sqlite3.connect
    connections = []

    def observe(database, *args, **kwargs):
        db = original(database, *args, **kwargs)
        if isinstance(database, str) and "mode=ro&immutable=1" in database:
            connections.append(database)
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                db.execute("CREATE TABLE attempted_write(value)")
        return db

    def forbidden(*args, **kwargs):
        pytest.fail("viewer attempted network access")

    monkeypatch.setattr(viewer.sqlite3, "connect", observe)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    invoke(approved)
    assert len(connections) == 1


def test_validation_only_needs_no_grant_or_report(approved):
    from pathlib import Path

    from superteacher.view_legacy_archive import ViewerError, validate_bundle

    _, request, grant, bundle_hash, _ = approved
    Path(request["receipt_path"]).unlink()
    result = validate_bundle(
        request["bundle_path"],
        expected_bundle_sha256=bundle_hash,
        expected_source_sha256=grant["source_sha256"],
        expected_owner_id=grant["owner_id"],
    )
    assert result == {"status": "validated", "counts": {"courses": 1, "sections": 1, "students": 2}}
    assert not Path(request["output_path"]).exists() and not Path(request["audit_path"]).exists()
    assert not list(Path(request["bundle_path"]).parent.glob(".legacy-view-*"))
    with pytest.raises(ViewerError):
        validate_bundle(
            request["bundle_path"],
            expected_bundle_sha256=bundle_hash,
            expected_source_sha256=grant["source_sha256"],
            expected_owner_id="foreign00000",
        )


@pytest.mark.parametrize("drift", ["null_owner", "type", "nullability", "foreign_key", "check", "index"])
def test_forged_schema_even_with_approved_hashes_refuses(approved, drift):
    import sqlite3
    from pathlib import Path

    from superteacher.view_legacy_archive import ViewerError

    def mutate(parts):
        path = Path(approved[1]["output_path"]).parent / "synthetic-schema-drift.db"
        path.write_bytes(parts["native.db"])
        path.chmod(0o600)
        with sqlite3.connect(path) as db:
            if drift == "index":
                db.execute("DROP INDEX uq_courses_owner_name")
            else:
                table = "students" if drift in {"nullability", "check"} else "courses"
                sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
                original, replacement = {
                    "null_owner": ("owner_id VARCHAR(12) NOT NULL", "owner_id VARCHAR(12)"),
                    "type": ("name VARCHAR(120)", "name TEXT"),
                    "nullability": ("name VARCHAR(120) NOT NULL", "name VARCHAR(120)"),
                    "foreign_key": ("ON DELETE CASCADE", "ON DELETE NO ACTION"),
                    "check": ("grade_level BETWEEN 1 AND 12 AND grade_level = CAST(grade_level AS INTEGER)", "1"),
                }[drift]
                assert original in sql
                db.execute("PRAGMA writable_schema=ON")
                db.execute(
                    "UPDATE sqlite_master SET sql=? WHERE type='table' AND name=?",
                    (sql.replace(original, replacement), table),
                )
        if drift == "null_owner":
            with sqlite3.connect(path) as db:
                db.execute("UPDATE courses SET owner_id=NULL")
        parts["native.db"] = path.read_bytes()
        manifest = json.loads(parts["manifest.json"])
        manifest["native_db_sha256"] = hashlib.sha256(parts["native.db"]).hexdigest()
        parts["manifest.json"] = json.dumps(manifest).encode()

    with pytest.raises(ViewerError):
        invoke(repack(approved, mutate))


def test_pending_audit_directory_is_durable_before_report_link(approved, monkeypatch):
    from pathlib import Path

    from superteacher import view_legacy_archive as viewer

    root = Path(approved[1]["output_path"]).parent
    out_dir, audit_dir = root / "reports", root / "audits"
    out_dir.mkdir(mode=0o700)
    audit_dir.mkdir(mode=0o700)
    approved[1]["output_path"] = str(out_dir / "history.txt")
    approved[1]["audit_path"] = str(audit_dir / "access.jsonl")
    refreshed = reset_request(approved)
    audited = audit_dir.stat()
    calls = []
    fsync, link = os.fsync, os.link

    def observed_sync(fd):
        info = os.fstat(fd)
        calls.append((info.st_dev, info.st_ino))
        fsync(fd)

    def observed_link(*args, **kwargs):
        assert (audited.st_dev, audited.st_ino) in calls, "pending audit directory not durable before report"
        link(*args, **kwargs)

    monkeypatch.setattr(viewer.os, "fsync", observed_sync)
    monkeypatch.setattr(viewer.os, "link", observed_link)
    invoke(refreshed)


@pytest.mark.parametrize("field", ["owner_id", "owner_email"])
def test_common_evidence_matches_importer_owner_input_contract(approved, field):
    import zipfile

    from superteacher import view_legacy_archive as viewer

    grant = dict(approved[2])
    with zipfile.ZipFile(approved[1]["bundle_path"]) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    manifest = json.loads(parts["manifest.json"])
    if field == "owner_id":
        grant["owner_id"] = "not-a-valid-native-owner"
        manifest["owner"]["id"] = grant["owner_id"]
    else:
        manifest["owner"]["email"] = None
    parts["manifest.json"] = json.dumps(manifest).encode()
    with pytest.raises(viewer.ViewerError):
        viewer._evidence(parts, viewer._Budget(), grant)


def test_schema_signature_only_normalizes_whitespace_and_constraint_order():
    from superteacher.view_legacy_archive import _schema_signature

    first = "CREATE TABLE t (a TEXT DEFAULT 'a  b', PRIMARY KEY (a), CHECK (a != 'private'))"
    reordered = "CREATE TABLE t (\n a TEXT DEFAULT 'a  b', CHECK (a != 'private'), PRIMARY KEY (a))"
    signature = _schema_signature([("table", "t", "t", first)])
    assert signature == _schema_signature([("table", "t", "t", reordered)])
    assert signature != _schema_signature([("table", "t", "t", first.replace("'a  b'", "'a b'"))])
    assert signature != _schema_signature([("table", "t", "t", first.replace("a TEXT", "a INTEGER"))])


@pytest.mark.parametrize("api", ["view", "validate"])
@pytest.mark.parametrize("state", ["changed", "missing"])
def test_runtime_importer_source_drift_refuses_before_helpers(approved, monkeypatch, api, state):
    from pathlib import Path

    from superteacher import view_legacy_archive as viewer

    root = Path(approved[1]["output_path"]).parent
    helper_source = root / "synthetic-importer.py"
    if state == "changed":
        helper_source.write_bytes(b"# different unsupported implementation\n")
    monkeypatch.setattr(viewer.importer, "__file__", str(helper_source))

    def forbidden(*args, **kwargs):
        pytest.fail("shared importer helper invoked with unsupported source")

    monkeypatch.setattr(viewer.importer, "_source_fingerprint", forbidden)
    monkeypatch.setattr(viewer.importer, "_parse", forbidden)
    with pytest.raises(viewer.ViewerError, match="Unsupported runtime importer source"):
        if api == "view":
            invoke(approved)
        else:
            viewer.validate_bundle(
                approved[1]["bundle_path"],
                expected_bundle_sha256=approved[3],
                expected_source_sha256=approved[2]["source_sha256"],
                expected_owner_id=approved[2]["owner_id"],
            )
    assert not Path(approved[1]["output_path"]).exists()
    assert not Path(approved[1]["audit_path"]).exists()
    assert not list(root.glob(".legacy-*"))
