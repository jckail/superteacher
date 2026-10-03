"""Offline viewer acceptance uses invented captures and private temporary files."""

import base64
import hashlib
import json
import os
import zlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    run(tmp_path, capture)
    return _approve_bundle(tmp_path)


def _approve_bundle(tmp_path):
    import zipfile

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
        "importer_version": manifest["importer_version"],
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
    producer = {
        "importer_sha256": viewer.CURRENT_RUNTIME_IMPORTER_SHA,
        "importer_version": "2",
        "native_revision": "0003",
    }
    parts = {"original_archive.json": raw, "manifest.json": json.dumps(producer).encode()}

    def forbidden(*args):
        pytest.fail("recursive importer was invoked before nested body guard")

    monkeypatch.setattr(viewer.importer, "_parse", forbidden)
    with pytest.raises(viewer.ViewerError, match="structural limit"):
        viewer._evidence(
            parts,
            viewer._Budget(),
            {**producer, "source_sha256": hashlib.sha256(raw).hexdigest(), "owner_id": "rehearsal001"},
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


# Exact published v1 source, compressed solely as a nonsecret synthetic-test fixture.
_FROZEN_V1_SOURCE = (
    "c-p-@Yj@i=mf!U&Fq{uVr4lVCX{U9oo#Q4->#ZAm?X;cN>*b+HNaBPdRX*Y<Ue9me`v5@jB`34p%{j46-~za~xNkfh$GKRok~ozj"
    "&x%s!(=1K)BHr$@y!={}8!56pUdL&Wh%nfdRStl18^mcrm7BOI0U(6xT!vX5d85%~E_VUI1){(|f>MfAo_&z12(#T@WK~(jkrdy>"
    "<%tM$iS>clW|5rzbv6@G3>`tA`w4@?D5D?`H}N|u;<U^}TtdwT;0XbOnLVG)CL%~9fQaNy!jH6sX}ptpyn@-3g}DCy^y%kcc;dR+"
    "?UMbd+ytfA1jUA01*wqlcS#(^rO575nF|=Fgt@`*Eb+wa4C-N~ak>^kUdF2+ECtlUM3W$tFloneMkAQzR`~v^LNfWjq9XL3W@S*u"
    "Sz3%nx-4G<X$q;o5tSrf>d$`^S*rie3jJ4Zz>D9LxRlS#Cv<QA-W&K*Zg;CVF|9tt{7HC5K=(4<N{!`DZ(dAHA%pCK5|Ppnm+;9I"
    "Rh~e(M>Ej1P*wm5OGO62Fi66U+-hc0OYO@PxJkBwJT5lKT%C6yvV5znuVqmHIn_{J5QbTm!Xm5c6hMO{{s4mkrzQ$2G84(G)ZfPI"
    "T&)RLBLgO;ix*i1bDO|OAp*f4Wra*N5kD0&S4|2;ENHbkOHHe@y4@Kdd-mhy#nqd|mH+eN>iX>BwU`U%*cttJ`gi~I>c#hGKQH`m"
    "e|@vKhVo}m#S?Knd-`1c8eLvp{JeO5`ufEJYVSt^{yA@f*_{*NByt^udw*9gfrI^E7yC+H{4`7bpv<;$=uEgxwgmLw$;i*;yBKMR"
    "9muFE^B{aXoy}&)Urx)<zwChHuQ-%8w1#0S_#p^VjQrz=*>)S32)bNK8O&DCzWO})LWa-fGJ5v(a~Xam{~A6EpGNYl<FB60o`1eF"
    "T>%9{=`Vvq`oK@v#ilHG#mUjp-QArB@;)u99Vn?%1~6*w!BDNXyF7a*(;#JBYxQK|2h!++mPoQaOf238YigAlEZza{M8q3D3RYEM"
    "PrINfWCS1&qn}UD&t9Isffe+BSp0fjFUT&3-txU)Y=WIEeCo%b$1KrX2WkXFqqizdU|c_r3cpI@-z#alW47w6Q3LIQI3H+L_}pzS"
    "S2CACsy40~O!qYi$n}r)S5E@yxlE)_UE-YkrZWUXy+GHyV4q|`^jKd90Ut(-A1~kh>c2Vt_M8OH<+e0JvBl;!duO>cUqM-dbs_dr"
    "CBRK}HJHVCy|EgzqB7q}23pQ9v$wJ?s|w^m(qJ;L2a5e=6|E&=J06WjG<$JQqJBpDW|8Mv?p{GNP}uY_KH;{Ga~-5{2?{V08Hfw0"
    "fP7j6E3m_$4#74}L@L2Hg7HjCFy&;{1PhQh<7CiAkz5I&+V2$@Wf!2Mn6=>+<^@>Kol|9*SqXrzpxg*i3lR+pHque(#Vb(Ir7*p5"
    "DgMiY80<-Rj%u{AMu=G3rJt%#SfMH@Q4$~Mdj*KRmEb}E8Ws8tf}rc6%%lK{&;bzcWFpL@6nP2}Rp=a`qw??9ptrN-KY;OZfC6S!"
    "qfhN`p!gOrp^+7G;1B5T^&HT`yFj2o%>WDIl&I$V<Hu>zMG}<#3f591nO55+@Dn1~BoU76p<om={zOejDU3~)y`A&l6F~+ZSTh9?"
    "O3S&zPj&cbv3S4BQjiq^DmPyx*&X^sNX!lBT3B+i+_$>$%v>2&m#Ab-7nlRg5&?&*b|RqbptOJ*3&<-xR|IEwZds^~#h>Qf+6B>E"
    "Ipe;?9j2QeOD4T&MRC~13i%GYPtXx%ggp9LxGg{eW)cwmqk|=2$sQf-u`xzg5%a@%m_w1i&?~I3o5&T&MUJXX;qYhiA^^gX<4<JU"
    "L1T0k3b6#2Sq5ow1m3z_11XPa1qxB6N&Hrd%YC^4tpMEvGnISK#(;P;s<yjAjadN0`zUDhH#w34^d|b&K@rBWDhd+dJReN{{8f;k"
    "&!(b|EHCD+GjU+ePn_`>S;XqT7BHOEA2<+oY*ba6`Ne(<@zq;YSmj2M&u}kFOOWoNE-$^f(7^7PRu@ZgajEG<Ji%Y+b)$V6Gc&7T"
    "1ZxVht%{NaumYW-$0ZG*6lV@A3LcP&u^KpaaAkF!t}@UXG&H(H?zlMvLrARjuKly?muFWlwgPY;z3Q=w%($eABV3BC@W8mihs)Kv"
    "^^X@X7p>L+J<A|8oS32Nd7GK=+?SH#H_|*5yDIBPL+B9GQ#RI+MY)b37{IPTBj9+%z_9w23?j6V+h8w(=pBls2q<;}K8Dz_N<+|i"
    "YZz9=xyqEf(p!7L+6e)VJ=NV0Qtm{IJ_@iuuvG{SQz3R4n3z2wimC}}kGNMbwq<~t8aV+cwXOn;vn{cy7eP}llJ6#+!Z^*kg-Dfd"
    "DJ)F4aNSp!BExix3-CUA217#lY0<3-8#UwF_do}Z$oUbxI>6vcWEkcyE;q=1s|c7Qb>T1i%@PJ*7yi}Di`VDBivQ-X*B7rY&d)D?"
    "slQ);dw%ia2Nb`2=>Yc@z`TIx_M|Z>K|H=9k>Pp|gYPtR$K$RW(ooz+lCBotHD#dzc37$gL21Dd__zb|m=Hd<g^&dCnmJtyUm(;9"
    "2wXVMC7~UQf&@GTfdrrh$SP2KNeppbp{0?Ry+atApTswF(TSEVlP=$fQbwGZT7o|vNu2c##=_RNMJI8Zt9A1bSGOC6e<qH55P~IS"
    "zwM91rk@M?)Y2eF(E<%BvWZzJt*GucxD+`nHqU9TfKn?sO)ZF8Uo||odX+l<3LwaeeI~vUNHgV-0nwg*{sq-&+Xvx>8$u0cJ;<jq"
    "{>*sXZ!MkwtfDVxGY5MM@dp;HRx78!y_ybt<Z3>sZUE!$?o%ej-H}TR;%2gC9;SohB3ohJspJNp$_={CZ|E3&Hk+LQ!tDuhS6=yn"
    "G=}n?UxTPL5N9Zj`6`x4<debIxPkMvir>#2r;Y#@;F9mHNCi7rc`~$9S^hN`$Kdy>k-|m)2jz9I#hAiCo-_Ivb8&M!8g$cJ{;-L`"
    "S`INdpWBW<yvxvA%+b-Hxq$FFM-Kdi9%@ql6G{0`AY)y0L`BC=Q{NG~Ua-Sdu&es+gOKkroOc^EC3GhmBeh~5=au7>F$4YHnzV#~"
    "0-ca<tn+bbG|2&6=+X$|af?NuO&uQtzql$1ShK{>9Fl`(BHjRp9l|&CV?jfK&mt3Kl@$bjrKu}OP*ob8vnPe&i9TUbgDPei+rc<F"
    "vb75b4RT;b-z080$&+n&iR_kBuG9MN<}v#!b=K0V8_HJNAgwH9x5`Q~T9w_rp>k#h(hfimy|F=2EC0>;gN`aVK<pa_!)xF~nTC5m"
    "iD5d0bE}w>O@B|D8e4?5maA)xAn?)c(7iz9$92Tr&9&6YYAx*JhVRaEu8An3O!9m|eTEydn7FR;4ii{vF;$AGcHReY?VF#6iVXsd"
    "f18U|@^)mqKR8b{i9%q^M{_gN>hD^|_x2R8D2FD^n%dbgU^|*BCX}0#QTuB?Nyfx{f@T1<Xc;Vnhb2O{VB`Bh8uE18B3ffWvZeKq"
    "El?!QfRXQ~Q6Ebx21CJu8P(Hh$=mH9!y}00TIek&Dj)N93}NBYwgFlO+CJ!*-9C9RDz7Oz&yg<Zzw`l;J99jPe>}iC&#GNfry+O9"
    "#aUITHEhs()G`>l+osLv9koZFSTm~iItew+qTKK53St~oPk=u#I+!_v=~knRKh<+nfeCVEha($J2UxO(>Ep?!S7ejzo4GLjslF{X"
    "g(ZGrwxtyTDKfXT3(b)v(0008YXd(`)iR6rP*h`#1%6eozEr$9$e#dbdy2!(z1r{ficJ9SFg5f*Rv^@J9T;f(CGf1bk?*5;4fJzK"
    "-L~-IrogSuh)j{AUQgcUCL4}9Y&#?07kQ~&6I@`*QR7%Wv$4~Is>#H{P!$mq)F=^Qk=G)LQ;p1EQCtM;TsER2knYAJ)T&{K`~cC^"
    "4jyq%fe|O^2oHRlJl>(#IA)h>Y)@Rd^+v70A3ZZ?<xPG&xX=0C#4@UIl?UssNjGRGk5Xt<k6({)2Q?r)b`<R5BUn3jaRh%y%OkZJ"
    "W*6ywua+x}TQU%#R7pa{)y>;|9Nqla(d}nPdN0qJ(D36HTm6*E_d5Uq3WXgGqa;f&H-XozC&S8dAdBD2PTb-KJGi}>5i4Dh588`F"
    "A<II?w_b|~jh>Egb!5Pvw3T`<S}An99Y#L}wHs=BdpqETputdWn@fnJkDJLCWS<VawZx{$(?^>a7O2};UWrzel&n$P9|F@d3OVXl"
    "?O`9~n$T)L&)A>G9I(M@BRa5(jY%AuGr)EUb#TV2Mc<qam!MykV=@=x;q5YBS6~A^X-;i4r#!V`A7R>Bxx;h#i0+OpWcAw3hX_9#"
    ";!)e3V`$|ubbR72qzMBoeXFWCez9Xd$I@TxxYQ9>!(%okLeFQwe)q1EtvqTcojdY1?a-}LWvEDgR^u4PFj;nOiwaH^D@CI<idy<M"
    "y&Ft1yS;JD*N7b_UgDl+*6PoOJzv$`Kv1XqP}Pj7R_Jxs#+<{z)Th)tIg~P^qf5A2YM{d|W~fd_Sy3bPACuc)QiTk5<HS*~o7XZ+"
    "H>cCzg6W6Z^ecaQ`x!6`bVuF;oqW)p!g}CwI!rdh(q#!ohCx9m_|k}SHZV1^zr7jOP(@#QrbrDK<E7c)S6ersJ!mW&+rg%x7eo>E"
    "*s=7hj*Yzsu!q{l_NSFwR*LOJ-8n~^H4ACGcw^4tJmMd52Ms3C44`^2S-K%RZ8M!d8drxIs_4d?_~96$K_Z(qwH;R9gFB1Bt2}4a"
    "e)s>9Q}keZ1BC7$T_Bc<IBGD;L!a{L&&O0L=U}>NFg(@@wasjp>(sa-C#Wx5MY@jVp&^X^Yys&BD<JjR1gh=HWZ2M*hqG6W#iZD>"
    "Gj(Gj8Zl-EOr4gQGf`STr%9tIA4Hw<)C!vQvr4VhE@9UZRXI|lLp9|lqE?*ufXE5+KKd%%q!u%vPG~)t4N5}IJ=nKOa9|uZ;q%47"
    "O^UADfD;A|D@#0Uc>ge|kJiEW&F!Q<)kgKqi0tbY$Yii;MXbinvpe`%aV&#v@xR?a_cz@C%`G5sukm~snKL_h00Nbyi`m$TQOOpE"
    "sKYqz@YXtaanm41v!mOdV;5r`7B}PJo0H?GJ<5*9R|+0U05f|HF)yASr$JUR@lldc()eq0B3P~vx)FZjH!65e+gqo+?9C)Y8s1uI"
    "QD&k}(@k)hcZiKSnjBeFv)50n#D*l?ch2?b!@o3Mw^k8Z;{kvMr7kec2qFO)+1n4u1|3Lk;d(2&5~EHMDv9ZB1mU4|0FQ|@*t>~}"
    "dm-@O&0q~p^wTz!CI>rv(zg%yi6a~s;<mS@OT^or^(4edQIJk^9cFSFIhx*v))ewu9H8%d=o945*!JXkK_7aCtkSnBC=A~WUC@C2"
    "D~0BqyXt3(=^;j#_6UPPW4#NUVVXKY7({X#hyG6Hv{&2Q!0E!9!@k%e1OW=xAKM@b_QfI4O}3SHS^m~1pY`KFP2%(*4zb@lh1~x4"
    "&?#*(;zLg&rz_sID(m0U1zuy=Kg|{Akg@NcQB-!USMwPS*id)}6`T?PghhNE&C^g|p#c>s83spL{T{05bFP<Q9ulOeD1#jQ8gcy}"
    "=XhR}57(!7daIDYO=TPw5SRd|a7Pc+8e1MP$l@-C1_dA5VoU6&!B#dSF@4;=TeG4p9wOfxqjBJ+W=G-HBRd2Ph~uD>YC`x=IA781"
    "!-^)b0Fcp_VO;#4x1c@zU1JYy&F3g_&U~}U3$ru@a=6aPR&KL=e`1;D5<XieVUvj5ow_SezL#MIzKV0bIA6SYBa-Y6{ItJ~LHQC+"
    "6L2V25<<@`1?R#}Os$YxlGYGb&tZ}k((MT@6&gCew3ZpeSPrqZ)Nmr6??gfPYV(qDPZ~j|)f>4bJeW;)Vzznhr74$BMbZWkJ<c2B"
    "4&L5CCFVA{eeLFe7imFh;k-xgI#IwRLt9DTTlrumj+8glz@T=9s1w~7ea)V3v@8I&&13zw7-$!^UMRFvb7A<qjzT9^R$`EI`|bo-"
    "Xf)CUc%)Qk4|UGKM72&w8q9?-l@kGM=IwQWQGp8qRgxI|I&Mpf!O&%3h8?$&)hwq*{g-*J(H}8gbKHZ>ry9dLV-(ow6K1b(O0+nS"
    "=~AaOYSuIBNvfUj(452MGD_XIxYXiHX6nAKn_O)c2?__7=`r4K5Wr@BGmS??pvCPfKs)&e)!xa>6|KyiZ7O;Mps2HCYBfxfvM*Vt"
    "Y6sF~N+`R7*Wx+ulTS^*K@shUr@Cv&_EG0@gt?W5iHL1n6qx<D<+nFcsCLX5m30n|W4&E&4MjEe@mEZs(WM7LH$;y`xyiF?y%EPx"
    "dq?^IGRk$5WM1D$?K902o{^u(cQTo`=5MkasJ_~Qd{`Oqn85Kx*A!V9@Zx|is=)@t_Q?}7O}@?RW6HrD_X?+t(12ya?FyRsL^Nbp"
    "Go~%J^~jb0>uWWXkiof5`g1lqmxS97xJ|7NqjNi*hnWbv%uFruKBG<`tRg;X-af_t;%agFMju*V{Qbqb{`;3JJl;MLv+N6fwgbx9"
    "sadJTQMa+@%}d+vPgmz2mjDIHQFG|dIAJ}<vx&5I4C1^2amI6qKn%Rq$f=xB$9Zes#CCa@dbudU$A!irqyzWrqj7tXy(C>u{+}P^"
    "z!|v@xVp~e)#-OXo}#eGc%AZHpNrS6jbf_<-ll3LE(jxa{oGwbEHbZK@Kpe=o9I8hr3Cc*u77C&w5xcj+y$X(E%v;%<a4w3<H7D$"
    "NmXpz@uA^-+|*-#)YT(eLqB-}oX3GbhAwg1b_W0VgDcO(9U7`O(SN{LEb7B!8NKrHV-Xv)LlxrvL)>ZKq_x?U!W6}xWIrHS-2351"
    "hHo7eq~JtoKj_AFvbWA;+(Nc-I^{t37WelIF#dRSRaB*SS<`AOUR_=M2s&SaT@8J`J=25#Y&Ls#U<Td%!0_<Et}G&2Fc^udz?;<e"
    "(49^Rm5y%38xysRHIs0E0J>~^o{SkwB~Rj)?-y4KqvtVQ@;3}p4RY;3mG0skKn*#ZuDm0U+xOhNI_S_6ul~}DwR2B>KRAEsLu&w&"
    "i7=;!l-%{_jQ%fh!VNAxy55RwNBGLduu;a?o-HybPJQ*jhRTV$?Dc|HmiQt}z?+~?>M5#|dA8~1zZ8@4htcU|8qFd7OMJzn*wDEg"
    "o$oW3s(w4W{2IIpy3+v@(8nV5{utgk+Nls!ozZVt+kT$4e9+Dej1$`4tDjB33Z|>u`!Ak9IGvfd&yJm1&+AYcCd3oKDtO?BdH6LQ"
    "!Y+E`M%WPYHMIw^4yGSYr@sO2xA(_S5plB_cK~B1@$u6ssFFMgk<k1`(Amq!v8E+QkGA<FjcYMP&lI_pbq8S5hZ199U~5E%!kH%H"
    "Q8a^>wW0G1>dGilJOErrHD*|Kv%8TZ=*j}j7GDZdVlwuEWsxN)yx<m6g#~NZ)=1lzJ8j?^qI=KNf@@s&9A+J)EjYe(b}^ynotmTZ"
    "i3Xa4r;eJq^q_z}l&NSj&`XORnvSWw<9o>ZmNwmhq}vW^m|hmjgFB4f?VGTQwA~4|_FbWA=M-^A#`V=eC5XKTg~#pt73O#_4$(Xr"
    "Gq?**7mO$bZQW361bPP}B_hN}?6?oAVmtOs;}uZFJl|v1PHmUv#)ml(?Wdb211;2<?34BeIPtyj<8@8nAJc_Xf4MK|-iW<Gt$x)m"
    "2j6_bSBUhjn5lWPiC=x12D^Cr?zpw#<LGywc&pMTBy@%;BD%Rqmtz{+nR;O+2e$@WgQ?7${jd~!di`_Klxi<kFJ<Yfz)5}KGR^MX"
    "pWeI}d-bi$HahAw2yKHxe9jwK6ZoUPrJ{Wh+7?C0w$8siw9!`FYt9q;5d6g<9jMTCttP~CI6kK-YWw7n&c?a3L*Qt|YoK&N8;dx?"
    "d`qFylI;bs)4aZt9{|;oH0tgWcX`4(Nz$SxpV-m6%GQ<Mo}GWo!D~-}E&~PT>`8Yo8SLGZA1xE7muLD^&)3EqqI@-9BH%Z?v?pO5"
    "8O7%ZtCS18o^4R)`})#ruwLij;FapKquR<Ayp=69|KqgGONb=80&lnXcK$jO^+Qsimhc6siKsV+@fb)cG1@5j@sXgyE10F$x<F5Q"
    "6bdhD*3a5CU5wV||3fo0)i3{fZzQ%2^8L&DMFe$O*kiYL%Dqo9lN0Cj9y^L5tueGse;v1_i(L>(ZS)OX>k>lY(UXm?X)xh8J(^(A"
    "68fq8Jkm<Vi<V9^`ZB4qXgQcDYq>j(4z%{a(P}GNnhQ1E^GnfkSY<c5T~_$;QF{_x>V1fJ%~>>3cMLSKb96dm*Gc6yl6Q@TuOGHp"
    "p`y7Pc%Y)uMm-DZ{TA<D!Eg1p0Jg@BJCM4ZvmkQ=cy{T(T)a9zeY1E;-Dg#~tICtXlRLEED)bvB!{>KgYrO%!MfJ&nc6vQMbV{JD"
    "b>d7{eaxFa)@idtqqS|J9u=LT{&wS&!S2*!A=WCKK?x=2#|InHweg(LC`;TsclG-nudWu~0lzSlh;P0T$6pNg#B1mA0R_5UzRGy5"
    "deUL))ro=38@*1kPs8E&PMXK|dt6$&=N8;`AFNQvD%jm&_2hJP3_YEs1*s99uQFO_9agB-ZXfEqcj^Zp&7rA@W&3KiQ6KSj&}Tv~"
    "0ElPD53G_oChtDr)_UR1hF$0|{_$7fnx>U&l+$kCImW|tHQ~Mn^8*ZIvI|OS-GLzQIQxL6rjA5-FAKv^l@`J0f5Aswznjzj^ppBk"
    "jGXTE^3%57X}+$|0$x%L(k9Gfn%La;qbvkZ*lNl7TGhl=ZlZGl!lLydu<2BLm{X<TCni+3wj~DIk`0;CzR#yNVkhrY+JW-|mWrD@"
    "_%IaF%0W*>`elyqc#4foc5`Q;Lh@uUxDiE>>U0u5{1V2yAW>w2(n4Q9%=yt?9JZh(?Aw&lF9r6eznZTGK|h{K0(2{E5p2}9oc=jM"
    "AB+UdJ_UgqTi*l2J0}(xy8}ItCIv^qIH8d8Q=wShj>U&084aLpiZnmHv(f^oP8WmgOmLWZLe)4g_CUKbg2Ij_Iv&;iShh?(+Sk}#"
    "oPktA0OQj!4c|u%>i9m&sP8-Kc}!9t*Lw(@w~P02>5>FPH~#~@Z*;T"
)


@pytest.fixture
def historical_approved(tmp_path, capture):
    from superteacher import db as database
    from superteacher import view_legacy_archive as viewer

    raw = zlib.decompress(base64.b85decode(_FROZEN_V1_SOURCE))
    assert hashlib.sha256(raw).hexdigest() == viewer.HISTORICAL_IMPORTER_SHA
    helper = tmp_path / "frozen-importer-v1.py"
    helper.write_bytes(raw)
    helper.chmod(0o400)
    namespace = {
        "__name__": "superteacher._synthetic_v1_importer",
        "__package__": "superteacher",
        "__file__": str(helper),
    }
    exec(compile(raw, str(helper), "exec"), namespace)
    # Test-only dependency seam: the unchanged v1 producer targets its original schema.
    # Production migration selection is explicit; it never depends on caller identity.
    namespace["run_migrations"] = lambda engine: database.run_migrations(engine, target_revision="0003")
    tmp_path.chmod(0o700)
    source = tmp_path / "source.json"
    source.write_bytes(json.dumps(capture, indent=2).encode())
    source.chmod(0o400)
    namespace["import_legacy_archive"](
        source,
        tmp_path / "bundle.zip",
        expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        owner_id="rehearsal001",
        owner_email="rehearsal@example.invalid",
    )
    return _approve_bundle(tmp_path)


def test_genuine_v1_artifact_and_unchanged_grant_remain_valid(historical_approved):
    from superteacher import view_legacy_archive as viewer

    _, request, grant, bundle_hash, _ = historical_approved
    before = {name: Path(request[name]).read_bytes() for name in ("receipt_path", "bundle_path")}
    assert grant["importer_version"] == "1" and grant["importer_sha256"] == viewer.HISTORICAL_IMPORTER_SHA
    assert (
        viewer.validate_bundle(
            request["bundle_path"],
            expected_bundle_sha256=bundle_hash,
            expected_source_sha256=grant["source_sha256"],
            expected_owner_id=grant["owner_id"],
        )["status"]
        == "validated"
    )
    assert invoke(historical_approved) == {"status": "created", "students": 1}
    assert all(Path(request[name]).read_bytes() == raw for name, raw in before.items())


@pytest.mark.parametrize("contract", ["current", "historical"])
def test_cross_supported_producer_grant_refuses_even_when_repinned(contract, request):
    from superteacher import view_legacy_archive as viewer

    approved = request.getfixturevalue("approved" if contract == "current" else "historical_approved")
    grant = approved[2]
    grant["importer_sha256"] = (
        viewer.HISTORICAL_IMPORTER_SHA if contract == "current" else viewer.CURRENT_RUNTIME_IMPORTER_SHA
    )
    grant["importer_version"] = "1" if contract == "current" else "2"
    changed = reset_request(approved)
    with pytest.raises(viewer.ViewerError, match="Approved producer mismatch"):
        invoke(changed)
    assert not Path(approved[1]["output_path"]).exists() and not Path(approved[1]["audit_path"]).exists()


def test_supported_digest_with_wrong_version_refuses(approved):
    from superteacher import view_legacy_archive as viewer

    approved[2]["importer_version"] = "1"
    with pytest.raises(viewer.ViewerError, match="Unsupported importer/schema"):
        invoke(reset_request(approved))


def test_current_audit_schema_cannot_masquerade_as_archive_0003(approved):
    from sqlalchemy import create_engine

    from superteacher import db as database
    from superteacher import view_legacy_archive as viewer

    def mutate(parts):
        path = Path(approved[1]["output_path"]).parent / "synthetic-current-head.db"
        path.write_bytes(parts["native.db"])
        path.chmod(0o600)
        engine = create_engine(f"sqlite:///{path}")
        try:
            database.run_migrations(engine)
            with engine.begin() as connection:
                assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0004"
                connection.exec_driver_sql("UPDATE alembic_version SET version_num='0003'")
        finally:
            engine.dispose()
        parts["native.db"] = path.read_bytes()
        manifest = json.loads(parts["manifest.json"])
        manifest["native_db_sha256"] = hashlib.sha256(parts["native.db"]).hexdigest()
        parts["manifest.json"] = json.dumps(manifest).encode()

    changed = repack(approved, mutate)
    with pytest.raises(viewer.ViewerError):
        invoke(changed)
    assert not Path(approved[1]["output_path"]).exists() and not Path(approved[1]["audit_path"]).exists()
