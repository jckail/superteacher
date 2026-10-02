"""Offline one-student text view; externally approved digests are trust inputs.

No grant is authenticated by this tool, and bundled ownership is a snapshot only.
Use synthetic data until a real actor/recipient and retention grant are approved.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
import unicodedata
import zipfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from . import import_legacy_archive as importer

MAX_BUNDLE = 128 * 1024 * 1024
MAX_CONTROL = 64 * 1024
MAX_REPORT = 256 * 1024
MAX_DEPTH = 64
MAX_NODES = 1_000_000
MEMBERS = {"native.db": 64 * 1024 * 1024, "manifest.json": 32 * 1024 * 1024, "original_archive.json": 32 * 1024 * 1024}
SUPPORTED_IMPORTER = "79784f1179f71be2772affadc1539ec56ee5f420c7f50d9a192434c9e06f6f37"
# Canonical 0001 -> 0003 synthetic importer DB: ordered sqlite_master
# (type,name,tbl_name,sql), canonical whitespace/independent constraint order.
# Includes every type/nullability/constraint/index expression; literals unchanged.
SUPPORTED_SQLITE_SCHEMA = "63db03652786bc231455830870cbf6a9cab85eb8ec18e62067b7f8bd7e8f335c"
AGGREGATES = {
    "gpa",
    "academic_performance.rank",
    "attendance_percentage",
    "attendance_days",
    "homework_points",
    "homework_completed",
}
TABLE_COLUMNS = {
    "alembic_version": {"version_num"},
    "ai_budget": {"day", "count"},
    "login_tokens": {"token_hash", "email", "created_at", "expires_at", "consumed_at", "ip_hash"},
    "users": {"id", "email", "created_at", "last_login_at", "disabled"},
    "courses": {"id", "owner_id", "name"},
    "sessions": {"id_hash", "user_id", "created_at", "expires_at", "last_seen_at"},
    "usage_counters": {"user_id", "day", "kind", "count"},
    "sections": {"id", "course_id", "name"},
    "assessments": {"id", "section_id", "title", "kind", "max_points", "due_date"},
    "students": {"id", "name", "grade_level", "section_id"},
    "attendance": {"id", "student_id", "day", "status"},
    "insights": {"student_id", "fingerprint", "model", "payload", "created_at"},
    "notes": {"id", "student_id", "body", "created_at"},
    "scores": {"id", "assessment_id", "student_id", "points"},
}
REQUEST_KEYS = {"version", "bundle_path", "receipt_path", "output_path", "audit_path", "owner_id", "aggregates"}
GRANT_KEYS = {
    "version",
    "authorization_reference",
    "actor",
    "operator_uid",
    "recipient_reference",
    "approved_at",
    "expires_at",
    "bundle_sha256",
    "source_sha256",
    "importer_version",
    "importer_sha256",
    "native_revision",
    "owner_id",
    "native_student_id",
    "source_student_id",
    "source_class_id",
    "source_section",
    "aggregates",
    "purpose",
    "identity_disposition",
    "retention_delivery_reference",
}


class ViewerError(RuntimeError):
    """Fixed, sanitized operator message only."""


def _require(ok, message="Viewer evidence validation failed."):
    if not ok:
        raise ViewerError(message)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _hash(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "Approved SHA256 is required.")
    return value


def _runtime_compatibility():
    """Source-available packaging only; this is compatibility, not attestation."""
    try:
        path = Path(importer.__file__)
        if not path.is_absolute() or path.suffix != ".py":
            raise ValueError
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > 128 * 1024:
                raise ValueError
            raw = source.read(128 * 1024 + 1)
            after = os.fstat(source.fileno())

        # Avoid calling any imported validation helper before proving its source
        # compatible. Access-time advances are allowed on unchanged source bytes.
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

        if len(raw) > 128 * 1024 or identity(before) != identity(after) or _digest(raw) != SUPPORTED_IMPORTER:
            raise ValueError
    except Exception:
        raise ViewerError("Unsupported runtime importer source.") from None


@contextmanager
def _parent(path):
    """Traverse each component with nofollow and anchor operations to its fd."""
    path = Path(path)
    _require(path.is_absolute() and ".." not in path.parts and path.name not in ("", "."), "Unsafe artifact path.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parent.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        info = os.fstat(fd)
        _require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700, "Artifact parent must be private.")
        yield fd, path.name
    finally:
        os.close(fd)


def _read(path, maximum):
    with (
        _parent(path) as (parent, name),
        os.fdopen(os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent), "rb") as stream,
    ):
        info = os.fstat(stream.fileno())
        _require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o400,
            "Frozen input must be a private standalone regular file.",
        )
        _require(info.st_size <= maximum, "Input exceeds viewer limit.")
        raw = stream.read(maximum + 1)
        _require(len(raw) <= maximum, "Input exceeds viewer limit.")
        _require(
            importer._source_fingerprint(info) == importer._source_fingerprint(os.fstat(stream.fileno())),
            "Input changed while reading.",
        )
        return raw, (info.st_dev, info.st_ino)


class _Budget:
    def __init__(self):
        self.remaining = MAX_NODES

    def parse(self, raw):
        # json.loads may allocate within the bounded byte size; do not invoke
        # importer's recursive finite/equivalence helpers before checking depth.
        def pairs(values):
            result = {}
            for key, value in values:
                _require(key not in result, "Duplicate JSON keys refused.")
                result[key] = value
            return result

        def invalid(_):
            raise ViewerError("Nonfinite JSON refused.")

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
        pending = [(value, 0)]
        while pending:
            child, depth = pending.pop()
            self.remaining -= 1
            _require(depth <= MAX_DEPTH and self.remaining >= 0, "JSON structural limit exceeded.")
            if isinstance(child, float):
                _require(child == child and abs(child) != float("inf"), "Nonfinite JSON refused.")
            elif isinstance(child, dict):
                self.remaining -= len(child)
                _require(self.remaining >= 0, "JSON structural limit exceeded.")
                pending.extend((item, depth + 1) for item in child.values())
            elif isinstance(child, list):
                pending.extend((item, depth + 1) for item in child)
        return value


def _bundle(raw):
    result = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        _require(len(entries) == 3 and {e.filename for e in entries} == MEMBERS.keys(), "Unsupported bundle members.")
        _require(sum(e.file_size for e in entries) <= MAX_BUNDLE, "Expanded bundle limit exceeded.")
        for entry in entries:
            mode = entry.external_attr >> 16
            _require(
                stat.S_ISREG(mode)
                and stat.S_IMODE(mode) == 0o600
                and not entry.flag_bits & 1
                and entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                "Unsafe ZIP member.",
            )
            _require(entry.file_size <= MEMBERS[entry.filename], "ZIP member exceeds viewer limit.")
            with archive.open(entry) as stream:
                data = stream.read(MEMBERS[entry.filename] + 1)
            _require(len(data) == entry.file_size and len(data) <= MEMBERS[entry.filename], "ZIP expansion refused.")
            result[entry.filename] = data
    return result


def _fields(values):
    _require(
        isinstance(values, list)
        and all(isinstance(v, str) for v in values)
        and len(set(values)) == len(values)
        and set(values) <= AGGREGATES,
        "Unsupported aggregate selection.",
    )
    return set(values)


def _grant(request, grant, bundle_hash, receipt_hash):
    _hash(receipt_hash)
    selectors = {"source_student_id", "native_student_id"} & request.keys()
    _require(
        len(selectors) == 1
        and request.keys() == REQUEST_KEYS | selectors
        and type(request["version"]) is int
        and request["version"] == 1,
        "Unsupported viewer request.",
    )
    _require(
        grant.keys() == GRANT_KEYS and type(grant["version"]) is int and grant["version"] == 1,
        "Unsupported approval receipt.",
    )
    _require(type(grant["operator_uid"]) is int and grant["operator_uid"] == os.getuid(), "Approval actor mismatch.")
    for key in GRANT_KEYS - {"version", "operator_uid", "aggregates"}:
        _require(isinstance(grant[key], str) and 0 < len(grant[key]) <= 1024, "Invalid approval field.")
    now = datetime.now(UTC)
    _require(
        importer._timestamp(grant["approved_at"]) <= now < importer._timestamp(grant["expires_at"]),
        "Approval is not current.",
    )
    selector = next(iter(selectors))
    _require(
        request["owner_id"] == grant["owner_id"] and request[selector] == grant[selector], "Approval scope mismatch."
    )
    _require(_fields(request["aggregates"]) <= _fields(grant["aggregates"]), "Aggregate grant mismatch.")
    _require(grant["bundle_sha256"] == bundle_hash, "Approved bundle digest mismatch.")
    _require(
        grant["purpose"] == "operator_history_review" and grant["identity_disposition"] == "verified_archive_review",
        "Unsupported approval purpose/disposition.",
    )
    _require(
        grant["importer_version"] == "1"
        and grant["importer_sha256"] == SUPPORTED_IMPORTER
        and grant["native_revision"] == "0003",
        "Unsupported importer/schema evidence.",
    )


def _evidence(parts, budget, grant, *, select_student=True):
    _runtime_compatibility()
    _require(
        isinstance(grant["owner_id"], str) and re.fullmatch(r"[A-Za-z0-9]{12}", grant["owner_id"]),
        "Explicit valid snapshot owner is required.",
    )
    raw = parts["original_archive.json"]
    _require(_digest(raw) == grant["source_sha256"], "Source digest mismatch.")
    archive = budget.parse(raw)
    manifest = budget.parse(parts["manifest.json"])
    # Every body is guarded before _parse decodes it again with recursive helpers.
    _require(isinstance(archive, dict) and isinstance(archive.get("responses"), list))
    for response in archive["responses"]:
        _require(isinstance(response, dict) and isinstance(response.get("body_utf8"), str))
        budget.parse(response["body_utf8"])
    classes, sections, students, selected = importer._parse(archive)
    rows, maps, changes, dispositions = importer._roster(
        classes, sections, students, grant["source_sha256"], grant["owner_id"]
    )
    expected = {
        "importer_version": "1",
        "importer_sha256": SUPPORTED_IMPORTER,
        "source_schema": "reviewed-edutrack-public-api-v1",
        "archive_field_dispositions": dict.fromkeys(importer._field_paths(archive), "retained_original_archive"),
        "native_revision": "0003",
        "source_sha256": grant["source_sha256"],
        "capture": {k: v for k, v in archive.items() if k != "responses"},
        "selected_response_indices": selected,
        "id_maps": maps,
        "normalization_changes": changes,
        "field_dispositions": dispositions,
        "counts": {key: len(value) for key, value in rows.items()},
        "limitations": [
            "Non-atomic API capture; completeness and deployed source provenance are unproven.",
            "Historical aggregates and unknown fields retained in original bytes only.",
            "No assessment, score, attendance, note, insight, authentication or usage events imported.",
        ],
        "native_db_sha256": _digest(parts["native.db"]),
    }
    _require(isinstance(manifest, dict) and manifest.keys() == expected.keys() | {"owner", "imported_at"})
    for key, value in expected.items():
        _require(importer._equivalent(manifest[key], value), "Manifest evidence mismatch.")
    owner = manifest["owner"]
    _require(
        isinstance(owner, dict)
        and owner.keys() == {"id", "email", "disabled"}
        and owner["id"] == grant["owner_id"]
        and type(owner["disabled"]) is bool
        and isinstance(owner["email"], str)
        and bool(owner["email"])
        and importer.normalize_email(owner["email"]) == owner["email"],
        "Manifest owner mismatch.",
    )
    importer._timestamp(manifest["imported_at"])
    if not select_student:
        return archive, manifest, rows, None
    sid = grant["source_student_id"]
    _require(maps["students"].get(sid) == grant["native_student_id"], "Student map mismatch.")
    chosen = [s for s in students if s["id"] == sid]
    _require(
        len(chosen) == 1
        and chosen[0]["class_id"] == grant["source_class_id"]
        and chosen[0]["section"] == grant["source_section"],
        "Student relationship mismatch.",
    )
    return archive, manifest, rows, chosen[0]


def _schema_signature(schema):
    """Canonicalize whitespace/constraint ordering, never SQL literal content.

    SQLAlchemy can reorder independent table constraints between processes.
    Parse only the reviewed CREATE TABLE envelope and comma-delimited top-level
    definitions; all expression/constraint/index tokens remain part of the pin.
    """
    canonical = []
    for kind, name, table, sql in schema:
        if sql is None:
            canonical.append((kind, name, table, None))
            continue
        quote, depth, pending_space = None, 0, False
        normalized, definitions, fragment = [], [], []
        match = re.fullmatch(r"CREATE\s+TABLE\s+(.+?)\s*\((.*)\)\s*", sql, re.S) if kind == "table" else None
        text = match[2] if match else sql
        i = 0
        while i < len(text):
            char = text[i]
            if quote:
                fragment.append(char)
                if char == quote:
                    if i + 1 < len(text) and text[i + 1] == quote:
                        fragment.append(text[i + 1])
                        i += 1
                    else:
                        quote = None
            elif char.isspace():
                pending_space = True
            else:
                if pending_space and fragment:
                    fragment.append(" ")
                pending_space = False
                if char in {"'", '"', "`"}:
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    _require(depth >= 0, "Unsupported schema syntax.")
                if match and char == "," and depth == 0:
                    definitions.append("".join(fragment).strip())
                    fragment = []
                else:
                    fragment.append(char)
            i += 1
        _require(quote is None and depth == 0, "Unsupported schema syntax.")
        if match:
            definitions.append("".join(fragment).strip())
            # Keep column order; normalize only independent constraint order.
            columns, constraints = [], []
            for definition in definitions:
                target = (
                    constraints if re.match(r"(?:CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN)\b", definition) else columns
                )
                target.append(definition)
            normalized = ["CREATE TABLE ", match[1].strip(), "(", ",".join(columns + sorted(constraints)), ")"]
        else:
            _require(kind == "index", "Unsupported schema object.")
            normalized = fragment
        canonical.append((kind, name, table, "".join(normalized)))
    return _digest(json.dumps(canonical, ensure_ascii=True, separators=(",", ":")).encode())


def _database(raw, parent_path, manifest, rows):
    # A new temporary directory is private; no bundled pathname is extracted.
    with tempfile.TemporaryDirectory(prefix=".legacy-view-", dir=parent_path) as directory:
        os.chmod(directory, 0o700)
        path = Path(directory) / "snapshot.db"
        with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "wb") as stream:
            stream.write(raw)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as db:
            db.enable_load_extension(False)
            db.execute("PRAGMA query_only=ON")
            db.execute("PRAGMA trusted_schema=OFF")
            steps = 0

            def progress():
                nonlocal steps
                steps += 1
                return steps > 20_000  # at most 20 million VM instructions

            db.set_progress_handler(progress, 1000)
            schema = db.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name,tbl_name"
            ).fetchall()
            signature = _schema_signature(schema)
            _require(signature == SUPPORTED_SQLITE_SCHEMA, "Unsupported database schema signature.")
            objects = [(kind, name, table) for kind, name, table, _ in schema]
            _require(
                {name for kind, name, _ in objects if kind == "table"} == TABLE_COLUMNS.keys()
                and all(kind in {"table", "index"} for kind, _, _ in objects),
                "Unsupported database schema.",
            )
            declarations = db.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall()
            _require(
                all(isinstance(sql, str) and re.match(r"CREATE\s+TABLE\b", sql, re.I) for (sql,) in declarations),
                "Unsupported database table declaration.",
            )
            for table, columns in TABLE_COLUMNS.items():
                _require(
                    {r[1] for r in db.execute(f'PRAGMA table_info("{table}")')} == columns,
                    "Unsupported database columns.",
                )
            _require(
                db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
                and db.execute("PRAGMA foreign_key_check").fetchone() is None,
                "Database integrity refused.",
            )
            _require(db.execute("SELECT version_num FROM alembic_version").fetchall() == [("0003",)])
            owner = manifest["owner"]
            _require(
                db.execute("SELECT id,email,disabled FROM users").fetchall()
                == [(owner["id"], owner["email"], int(owner["disabled"]))],
                "Database owner mismatch.",
            )
            for table, fields in {
                "courses": ("id", "name", "owner_id"),
                "sections": ("id", "course_id", "name"),
                "students": ("id", "name", "grade_level", "section_id"),
            }.items():
                actual = db.execute(f'SELECT {",".join(fields)} FROM "{table}"').fetchall()
                _require(
                    sorted(actual)
                    == sorted(tuple(owner["id"] if k == "owner_id" else row[k] for k in fields) for row in rows[table]),
                    "Database roster mismatch.",
                )
            for table in importer.EMPTY_TABLES:
                _require(
                    db.execute(f'SELECT count(*) FROM "{table}"').fetchone() == (0,), "Unsupported native event data."
                )


def _text(value):
    _require(isinstance(value, str))
    return "".join(
        f"\\u{ord(c):04x}" if unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} else c for c in value
    )


def _render(archive, student, grant, aggregates):
    lines = []
    used = 0

    def add(value):
        nonlocal used
        raw = (value + "\n").encode("utf-8")
        used += len(raw)
        _require(used <= MAX_REPORT, "Selected history exceeds report limit.")
        lines.append(raw)

    add("Retained legacy history — operator snapshot review only")
    for label, value in [
        ("Student", student["name"]),
        ("Source identity", student["id"]),
        ("Native identity", grant["native_student_id"]),
        ("Source class", student["class_id"]),
        ("Source section", student["section"]),
    ]:
        add(f"{label}: {_text(value)}")
    add(f"Capture interval: {_text(archive['started_at'])} to {_text(archive['completed_at'])}")
    add(f"Observed revision: {_text(archive['observed_revision'])}")
    version = archive["version_response"]
    add(f"Captured version: {_text(version['version'])}; reported commit: {_text(version['git_commit'])}")
    add(f"Historical schema candidate: {_text(archive['schema_candidate_commit'])} (not deployed-image proof)")
    add("Non-atomic capture; completeness and deployed-image source provenance are unproven.")
    add("Labels may overwrite prior entries and need not identify distinct events.")
    add("Dates and raw points/denominators are unavailable; capture time is not an assessment date.")
    add("These observations do not change native grades, GPA, attendance, risk or AI context.")
    performance = student.get("academic_performance")
    _require(isinstance(performance, dict), "Unsupported selected history shape.")
    for kind in ("tests", "homework"):
        values = performance.get(kind)
        _require(isinstance(values, dict), "Unsupported selected history shape.")
        add(f"{kind}:")
        if not values:
            add("  (empty)")
        for label, value in values.items():
            _require(isinstance(label, str) and isinstance(value, str), "Unsupported selected history value.")
            add(f"  {_text(label)}: {_text(value)} [retained historical percentage string]")
    for field in aggregates:
        container, key = (performance, "rank") if field == "academic_performance.rank" else (student, field)
        if key not in container:
            value = "(missing)"
        elif container[key] is None:
            value = "null"
        else:
            item = container[key]
            _require(isinstance(item, (str, int, float)) and not isinstance(item, bool), "Unsupported aggregate shape.")
            value = _text(item) if isinstance(item, str) else json.dumps(item, allow_nan=False)
        add(f"{field}: {value} [retained legacy aggregate]")
    return b"".join(lines)


def _publish(request, grant, report, bundle_hash):
    with (
        _parent(request["output_path"]) as (out_dir, out_name),
        _parent(request["audit_path"]) as (audit_dir, audit_name),
    ):
        _require(
            (os.fstat(out_dir).st_dev, os.fstat(out_dir).st_ino, out_name)
            != (os.fstat(audit_dir).st_dev, os.fstat(audit_dir).st_ino, audit_name),
            "Output paths must be distinct.",
        )
        # Refuse even dangling links; never replace an existing report.
        try:
            os.stat(out_name, dir_fd=out_dir, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ViewerError("Output already exists.")
        temp_name = ".legacy-report-" + os.urandom(16).hex()
        fd = os.open(temp_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=out_dir)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(report)
                stream.flush()
                os.fsync(stream.fileno())
            audit_fd = os.open(
                audit_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=audit_dir
            )
            with os.fdopen(audit_fd, "wb") as audit:
                entry = {
                    "status": "pending_publication",
                    "at": datetime.now(UTC).isoformat(),
                    "actor": grant["actor"],
                    "authorization_reference": grant["authorization_reference"],
                    "recipient_reference": grant["recipient_reference"],
                    "bundle_sha256": bundle_hash,
                    "source_sha256": grant["source_sha256"],
                    "source_student_id": grant["source_student_id"],
                    "native_student_id": grant["native_student_id"],
                    "owner_id": grant["owner_id"],
                    "disposition": grant["identity_disposition"],
                    "report_sha256": _digest(report),
                    "retention_delivery_reference": grant["retention_delivery_reference"],
                }
                audit.write((json.dumps(entry, ensure_ascii=True) + "\n").encode())
                audit.flush()
                os.fsync(audit.fileno())
                # The pending audit name must survive a crash even when report
                # and audit live in different directories.
                os.fsync(audit_dir)
                try:
                    os.link(temp_name, out_name, src_dir_fd=out_dir, dst_dir_fd=out_dir, follow_symlinks=False)
                    os.fsync(out_dir)
                except BaseException:
                    audit.write(b'{"status":"publication_failed"}\n')
                    audit.flush()
                    os.fsync(audit.fileno())
                    raise
                audit.write(b'{"status":"published_locally_not_delivered"}\n')
                audit.flush()
                os.fsync(audit.fileno())
                os.fsync(audit_dir)
        finally:
            os.unlink(temp_name, dir_fd=out_dir)


def view_legacy_archive(request_file, *, expected_bundle_sha256, expected_receipt_sha256):
    """Only approved offline snapshot review; returns content-free status."""
    try:
        _runtime_compatibility()
        bundle_hash, receipt_hash = _hash(expected_bundle_sha256), _hash(expected_receipt_sha256)
        budget = _Budget()
        request_raw, request_identity = _read(request_file, MAX_CONTROL)
        request = budget.parse(request_raw)
        _require(isinstance(request, dict))
        # Validate shape before using any private request pathname.
        selectors = {"source_student_id", "native_student_id"} & request.keys()
        _require(len(selectors) == 1 and request.keys() == REQUEST_KEYS | selectors, "Unsupported viewer request.")
        receipt_raw, receipt_identity = _read(request["receipt_path"], MAX_CONTROL)
        _require(_digest(receipt_raw) == receipt_hash, "Approval receipt digest mismatch.")
        grant = budget.parse(receipt_raw)
        _require(isinstance(grant, dict))
        _grant(request, grant, bundle_hash, receipt_hash)
        bundle_raw, bundle_identity = _read(request["bundle_path"], MAX_BUNDLE)
        _require(len({request_identity, receipt_identity, bundle_identity}) == 3, "Input aliases refused.")
        _require(_digest(bundle_raw) == bundle_hash, "Approved bundle digest mismatch.")
        for key in ("output_path", "audit_path"):
            with _parent(request[key]) as (parent, name):
                try:
                    os.stat(name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise ViewerError("Output already exists.")
        parts = _bundle(bundle_raw)
        archive, manifest, rows, student = _evidence(parts, budget, grant)
        # Use the descriptor-pinned parent via /proc so parent replacement cannot
        # redirect temporary database bytes into an unchecked directory.
        with _parent(request["output_path"]) as (parent, _):
            _database(parts["native.db"], f"/proc/self/fd/{parent}", manifest, rows)
        report = _render(archive, student, grant, request["aggregates"])
        # Confirm frozen inputs unchanged before publication; atime may advance.
        for path, original, limit in (
            (request_file, request_raw, MAX_CONTROL),
            (request["receipt_path"], receipt_raw, MAX_CONTROL),
            (request["bundle_path"], bundle_raw, MAX_BUNDLE),
        ):
            _require(_read(path, limit)[0] == original, "Input changed before publication.")
        _publish(request, grant, report, bundle_hash)
        return {"status": "created", "students": 1}
    except ViewerError:
        raise
    except Exception:
        raise ViewerError("Viewer refused invalid evidence or artifact operation.") from None


def validate_bundle(bundle_file, *, expected_bundle_sha256, expected_source_sha256, expected_owner_id):
    """Check preserved evidence only; grants no access and creates no report/audit.

    Returns content-free roster counts. Private input still requires an authorized
    operator; this helper proves compatibility, not recipient entitlement.
    """
    try:
        _runtime_compatibility()
        bundle_hash, source_hash = _hash(expected_bundle_sha256), _hash(expected_source_sha256)
        _require(
            isinstance(expected_owner_id, str) and re.fullmatch(r"[A-Za-z0-9]{12}", expected_owner_id),
            "Explicit valid snapshot owner is required.",
        )
        raw, _ = _read(bundle_file, MAX_BUNDLE)
        _require(_digest(raw) == bundle_hash, "Approved bundle digest mismatch.")
        parts = _bundle(raw)
        _, manifest, rows, _ = _evidence(
            parts, _Budget(), {"source_sha256": source_hash, "owner_id": expected_owner_id}, select_student=False
        )
        with _parent(bundle_file) as (parent, _):
            _database(parts["native.db"], f"/proc/self/fd/{parent}", manifest, rows)
        _require(_read(bundle_file, MAX_BUNDLE)[0] == raw, "Input changed during validation.")
        return {"status": "validated", "counts": {key: len(value) for key, value in rows.items()}}
    except ViewerError:
        raise
    except Exception:
        raise ViewerError("Viewer refused invalid evidence or artifact operation.") from None


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ViewerError("Invalid viewer arguments.")


def main(argv=None):
    parser = _Parser(description=__doc__)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--expected-bundle-sha256", required=True)
    parser.add_argument("--expected-receipt-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        result = view_legacy_archive(
            args.request_file,
            expected_bundle_sha256=args.expected_bundle_sha256,
            expected_receipt_sha256=args.expected_receipt_sha256,
        )
    except ViewerError as error:
        print(f"Viewer refused: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
