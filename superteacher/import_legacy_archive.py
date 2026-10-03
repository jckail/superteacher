"""Offline roster-only import; the original capture remains the historical record.

Prepare a separate frozen copy outside Git: create a mode0700 directory, copy the
archive into it, chmod the copy 0400, and independently verify its SHA256. Supply
that hash and an explicit owner to this tool. No existing artifact is replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from .accounts import normalize_email
from .db import run_migrations
from .models import Course, Section, Student, User
from .schemas import CourseIn, SectionIn, StudentIn

IMPORTER_VERSION = "2"
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
PROVENANCE = {
    "kind": "legacy_public_api_archive_non_atomic",
    "observed_revision": "edutrack-00018-t58",
    "observed_service": "edutrack",
    "schema_candidate_commit": "bbeea0f395a6ec4ebd325ec9e7c3c2de9193045f",
    "source_base_url": "https://www.the-super-teacher.com",
    "source_provenance": "historical_candidate_not_deployed_image_proof",
    "validation_status": "passed",
}
VALIDATION_KEYS = {
    "primary_shapes_valid",
    "section_shapes_valid",
    "repeat_shapes_valid",
    "class_ids_unique",
    "student_ids_unique",
    "section_pairs_unique",
    "students_class_references_valid",
    "students_section_references_valid",
    "sections_class_references_valid",
    "class_ids_stable_on_repeat",
    "student_ids_stable_on_repeat",
    "classes_payload_stable_on_repeat",
    "students_payload_stable_on_repeat",
}
EMPTY_TABLES = (
    "assessments",
    "scores",
    "attendance",
    "notes",
    "insights",
    "sessions",
    "login_tokens",
    "usage_counters",
    "ai_budget",
)


class LegacyImportError(RuntimeError):
    """Sanitized operator-safe failure, never containing a source record."""


def _require(condition, message="Archive schema or roster validation failed."):
    if not condition:
        raise LegacyImportError(message)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Archive contains duplicate JSON object keys.")
        result[key] = value
    return result


def _json(data):
    def invalid(_):
        raise LegacyImportError("Archive contains nonfinite JSON numbers.")

    result = json.loads(data, object_pairs_hook=_pairs, parse_constant=invalid)

    # Exponent overflow is not handled by parse_constant.
    def finite(value):
        if isinstance(value, float):
            _require(value == value and abs(value) != float("inf"), "Archive contains nonfinite JSON numbers.")
        elif isinstance(value, dict):
            for child in value.values():
                finite(child)
        elif isinstance(value, list):
            for child in value:
                finite(child)

    finite(result)
    return result


def _equivalent(left, right):
    # Canonical JSON preserves booleans/integers/floats unlike Python equality.
    return json.dumps(left, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    )


def _no_symlinks(path):
    _require(not any(part.is_symlink() for part in (path, *path.parents)), "Artifact paths must not use symlinks.")


def _private_directory(path):
    _no_symlinks(path)
    info = path.stat()
    _require(
        stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
        "Artifact directory must be owned by the operator and mode0700.",
    )


def _source_fingerprint(info):
    # Reading may advance atime on an unchanged frozen source (e.g. relatime).
    # Keep identity, access policy and content/change metadata in the guard.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_source(path):
    _no_symlinks(path)
    _private_directory(path.parent)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        _require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o400,
            "Source must be a private read-only standalone file without aliases.",
        )
        _require(info.st_size <= MAX_ARCHIVE_BYTES, "Archive exceeds the bounded input size.")
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
        _require(len(data) <= MAX_ARCHIVE_BYTES, "Archive exceeds the bounded input size.")
        _require(
            _source_fingerprint(os.fstat(stream.fileno())) == _source_fingerprint(info), "Source changed while reading."
        )
    return data


def _identity(value):
    _require(isinstance(value, str) and 0 < len(value) <= 256 and not any(ord(c) < 32 for c in value))
    _require(not any("\ud800" <= c <= "\udfff" for c in value))
    return value


def _timestamp(value):
    _require(isinstance(value, str))
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(parsed.tzinfo is not None)
    return parsed


def _field_paths(value, prefix=""):
    """Every object key is accounted for; opaque historical keys stay private."""
    paths = []
    if isinstance(value, dict):
        for key, child in value.items():
            pointer = prefix + "/" + key.replace("~", "~0").replace("/", "~1")
            paths.append(pointer)
            paths.extend(_field_paths(child, pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            paths.extend(_field_paths(child, prefix + "/" + str(index)))
    return paths


def _parse(archive):
    """Validate every response, then select first responses and verify repeats."""
    _require(isinstance(archive, dict))
    for key in (
        "started_at",
        "completed_at",
        "kind",
        "observed_revision",
        "observed_service",
        "schema_candidate_commit",
        "source_base_url",
        "source_provenance",
        "validation_status",
    ):
        _require(key in archive and archive[key] is not None)
    _require(isinstance(archive["consistency_limits"], list) and isinstance(archive["validation"], dict))
    _require(
        all(archive.get(key) == value for key, value in PROVENANCE.items()),
        "Archive provenance does not match the reviewed observed schema.",
    )
    _require(
        archive["validation"].keys() >= VALIDATION_KEYS
        and all(value is True for value in archive["validation"].values()),
        "Recorded archive validation did not pass.",
    )
    capture_start, capture_end = _timestamp(archive["started_at"]), _timestamp(archive["completed_at"])
    _require(capture_start <= capture_end)
    _require(all(isinstance(value, str) for value in archive["consistency_limits"]))
    base = archive["source_base_url"]
    _require(isinstance(base, str) and urlsplit(base).scheme in ("http", "https"))
    _require(isinstance(archive["responses"], list) and 4 <= len(archive["responses"]) <= 10000)
    groups = {}
    previous_end = capture_start
    for index, response in enumerate(archive["responses"]):
        _require(isinstance(response, dict) and type(response["status"]) is int and response["status"] == 200)
        start, end = _timestamp(response["started_at"]), _timestamp(response["completed_at"])
        _require(previous_end <= start <= end <= capture_end, "Capture response time provenance is invalid.")
        previous_end = end
        body = response["body_utf8"]
        _require(isinstance(body, str))
        _require(
            hashlib.sha256(body.encode("utf-8")).hexdigest() == response["body_sha256"],
            "Captured response hash verification failed.",
        )
        payload = _json(body)
        _require(_equivalent(payload, response["payload"]), "Captured body and decoded payload disagree.")
        url = response["url"]
        _require(isinstance(url, str) and url.startswith(base.rstrip("/") + "/"))
        parsed = urlsplit(url)
        _require(not parsed.query and not parsed.fragment)
        path = parsed.path
        _require(
            path in ("/api/version", "/api/db/classes", "/api/db/students")
            or re.fullmatch(r"/api/db/classes/[^/]+/sections", path),
            "Unexpected captured response path.",
        )
        if path in groups:
            _require(_equivalent(payload, groups[path][0]), "Repeated captured response sets changed.")
            groups[path][1].append(index)
        else:
            groups[path] = [payload, [index]]
    _require(
        len(groups["/api/version"][1]) == 1
        and len(groups["/api/db/classes"][1]) == 2
        and len(groups["/api/db/students"][1]) == 2,
        "Capture must contain one version and primary/repeated roster responses.",
    )
    _require(
        groups["/api/version"][1] == [0]
        and groups["/api/db/classes"][1][0] == 1
        and groups["/api/db/students"][1][0] == 2,
        "Capture response ordering is ambiguous.",
    )
    _require(
        groups["/api/db/classes"][1][-1] == len(archive["responses"]) - 2
        and groups["/api/db/students"][1][-1] == len(archive["responses"]) - 1
    )
    version = groups["/api/version"][0]
    _require(
        isinstance(version, dict)
        and all(isinstance(version.get(key), str) and version[key] for key in ("version", "git_commit")),
        "Captured version provenance is invalid.",
    )
    _require(_equivalent(archive["version_response"], version), "Version response metadata disagrees with capture.")
    classes = groups["/api/db/classes"][0]["classes"]
    students = groups["/api/db/students"][0]
    _require(isinstance(classes, list) and isinstance(students, list))
    sections = []
    class_ids = set()
    for course in classes:
        _require(isinstance(course, dict))
        cid = _identity(course["id"])
        _require(re.fullmatch(r"[A-Za-z0-9_-]+", cid), "Class identity cannot be resolved as an endpoint segment.")
        _require(cid not in class_ids, "Duplicate source class identities.")
        class_ids.add(cid)
        path = f"/api/db/classes/{cid}/sections"
        _require(len(groups[path][1]) == 1)
        values = groups[path][0]["sections"]
        _require(isinstance(values, list))
        for section in values:
            _require(isinstance(section, dict) and section["class_id"] == cid)
            sections.append(section)
    _require(
        set(groups) - {"/api/version", "/api/db/classes", "/api/db/students"}
        == {f"/api/db/classes/{cid}/sections" for cid in class_ids}
    )
    _require(isinstance(archive["counts"], dict))
    for key, count in (
        ("classes", len(classes)),
        ("sections", len(sections)),
        ("students", len(students)),
        ("responses", len(archive["responses"])),
    ):
        _require(
            type(archive["counts"].get(key)) is int and archive["counts"][key] == count,
            "Recorded roster counts disagree with validated capture.",
        )
    return classes, sections, students, {key: value[1] for key, value in groups.items()}


def _roster(classes, sections, students, source_hash, owner_id):
    maps = {"courses": {}, "sections": [], "students": {}}
    changes, dispositions, rows, used = [], [], {"courses": [], "sections": [], "students": []}, {owner_id}

    def allocate(kind, identity):
        value = hashlib.sha256(json.dumps([source_hash, kind, identity], ensure_ascii=True).encode()).hexdigest()[:12]
        _require(value not in used, "Native identifier collision; import refused.")
        used.add(value)
        return value

    def account(kind, identity, record, mapped, normalized):
        dispositions.append(
            {
                "kind": kind,
                "source_identity": identity,
                "retained_field_paths": [
                    path
                    for key, value in record.items()
                    if key not in mapped
                    for path in (
                        [
                            "/" + key.replace("~", "~0").replace("/", "~1"),
                            *_field_paths(value, "/" + key.replace("~", "~0").replace("/", "~1")),
                        ]
                    )
                ],
                "fields": {key: ("imported" if key in mapped else "retained_original_archive") for key in record},
                "unknown_fields": sorted(
                    set(record)
                    - mapped
                    - {
                        "gpa",
                        "academic_performance",
                        "attendance_percentage",
                        "attendance_days",
                        "homework_points",
                        "homework_completed",
                        "ai_insights",
                    }
                ),
            }
        )
        for key, value in normalized.items():
            if value != record[key]:
                changes.append(
                    {"kind": kind, "source_identity": identity, "field": key, "original": record[key], "native": value}
                )

    # Preflight target SQLite uniqueness semantics before any native row writes.
    course_names = set()
    section_names = set()
    for record in classes:
        cid = record["id"]
        _require(isinstance(record["name"], str) and not any("\ud800" <= c <= "\udfff" for c in record["name"]))
        name = CourseIn(name=record["name"]).name
        comparator = sqlite3.connect(":memory:")
        try:
            folded = comparator.execute("SELECT lower(?)", (name,)).fetchone()[0]
        finally:
            comparator.close()
        _require(folded not in course_names, "Course normalization creates a uniqueness collision.")
        course_names.add(folded)
        native = allocate("course", cid)
        maps["courses"][cid] = native
        rows["courses"].append({"id": native, "name": name})
        account("course", cid, record, {"id", "name"}, {"name": name})
    section_map = {}
    for record in sections:
        key = (record["class_id"], _identity(record["name"]))
        _require(key not in section_map, "Duplicate or ambiguous source sections.")
        name = SectionIn(course_id=maps["courses"][key[0]], name=key[1]).name
        _require((key[0], name) not in section_names, "Section normalization creates a uniqueness collision.")
        section_names.add((key[0], name))
        native = allocate("section", key)
        section_map[key] = native
        maps["sections"].append({"class_id": key[0], "name": key[1], "native_id": native})
        rows["sections"].append({"id": native, "course_id": maps["courses"][key[0]], "name": name})
        account("section", key, record, {"class_id", "name"}, {"name": name})
    for record in students:
        _require(isinstance(record, dict))
        sid = _identity(record["id"])
        _require(sid not in maps["students"], "Duplicate source student identities.")
        key = (_identity(record["class_id"]), _identity(record["section"]))
        _require(key in section_map, "Student class/section reference is missing or ambiguous.")
        _require(type(record["grade"]) is int, "Student grade must be an integer from 1 through 12.")
        _require(isinstance(record["name"], str) and not any("\ud800" <= c <= "\udfff" for c in record["name"]))
        validated = StudentIn(name=record["name"], grade_level=record["grade"], section_id=section_map[key])
        native = allocate("student", sid)
        maps["students"][sid] = native
        rows["students"].append({"id": native, **validated.model_dump()})
        account("student", sid, record, {"id", "name", "grade", "class_id", "section"}, {"name": validated.name})
    return rows, maps, changes, dispositions


def _database(path, rows, owner_id, email, disabled):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    engine = create_engine(URL.create("sqlite", database=str(path)), hide_parameters=True)
    try:
        run_migrations(engine, target_revision="0003")
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
            with Session(bind=connection) as session, session.begin():
                session.add(User(id=owner_id, email=email, disabled=disabled))
                session.flush()
                session.add_all(Course(owner_id=owner_id, **row) for row in rows["courses"])
                session.flush()
                session.add_all(Section(**row) for row in rows["sections"])
                session.flush()
                session.add_all(Student(**row) for row in rows["students"])
                session.flush()
        with sqlite3.connect(path) as connection:
            _require(connection.execute("PRAGMA integrity_check").fetchall() == [("ok",)])
            _require(not connection.execute("PRAGMA foreign_key_check").fetchall())
            _require(connection.execute("SELECT version_num FROM alembic_version").fetchall() == [("0003",)])
            _require(
                connection.execute("SELECT id,email,disabled FROM users").fetchall()
                == [(owner_id, email, int(disabled))]
            )
            _require(
                connection.execute("SELECT count(*) FROM courses WHERE owner_id != ?", (owner_id,)).fetchone()[0] == 0
            )
            for table in EMPTY_TABLES:
                _require(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == 0)
            for table, expected in rows.items():
                _require(connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] == len(expected))
    finally:
        engine.dispose()


def import_legacy_archive(source, destination, *, expected_sha256, owner_id, owner_email, owner_disabled=True):
    """Publish one complete private ZIP; reject all invalid roster exceptions."""
    try:
        _require(
            isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256),
            "An explicit lowercase source SHA256 is required.",
        )
        _require(
            isinstance(owner_id, str) and re.fullmatch(r"[a-zA-Z0-9]{12}", owner_id),
            "An explicit valid 12-character owner ID is required.",
        )
        email = normalize_email(owner_email)
        _require(email is not None, "An explicit valid owner email is required.")
        _require(type(owner_disabled) is bool, "Owner disabled state must be explicit boolean.")
        source, destination = Path(source).absolute(), Path(destination).absolute()
        _no_symlinks(destination)
        _private_directory(destination.parent)
        _require(
            not os.path.lexists(destination) and source.resolve() != destination.resolve(),
            "Destination must be new and must not alias the source.",
        )
        raw = _read_source(source)
        _require(hashlib.sha256(raw).hexdigest() == expected_sha256, "Source SHA256 verification failed.")
        archive = _json(raw)
        classes, sections, students, selected = _parse(archive)
        rows, maps, changes, dispositions = _roster(classes, sections, students, expected_sha256, owner_id)
        manifest = {
            "importer_version": IMPORTER_VERSION,
            "importer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_schema": "reviewed-edutrack-public-api-v1",
            "archive_field_dispositions": dict.fromkeys(_field_paths(archive), "retained_original_archive"),
            "native_revision": "0003",
            "source_sha256": expected_sha256,
            "imported_at": datetime.now(UTC).isoformat(),
            "capture": {k: v for k, v in archive.items() if k != "responses"},
            "selected_response_indices": selected,
            "owner": {"id": owner_id, "email": email, "disabled": owner_disabled},
            "id_maps": maps,
            "normalization_changes": changes,
            "field_dispositions": dispositions,
            "counts": {key: len(value) for key, value in rows.items()},
            "limitations": [
                "Non-atomic API capture; completeness and deployed source provenance are unproven.",
                "Historical aggregates and unknown fields retained in original bytes only.",
                "No assessment, score, attendance, note, insight, authentication or usage events imported.",
            ],
        }
        with tempfile.TemporaryDirectory(prefix=".legacy-import-", dir=destination.parent) as directory:
            workspace = Path(directory)
            os.chmod(workspace, 0o700)
            db = workspace / "native.db"
            _database(db, rows, owner_id, email, owner_disabled)
            manifest["native_db_sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
            bundle = workspace / "bundle.zip"
            fd = os.open(bundle, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as output:
                    for name, data in (
                        ("native.db", db.read_bytes()),
                        ("manifest.json", json.dumps(manifest, ensure_ascii=True, allow_nan=False).encode()),
                        ("original_archive.json", raw),
                    ):
                        info = zipfile.ZipInfo(name)
                        info.external_attr = (stat.S_IFREG | 0o600) << 16
                        output.writestr(info, data)
                stream.flush()
                os.fsync(stream.fileno())
            _require(_read_source(source) == raw, "Source changed before publication.")
            os.link(bundle, destination, follow_symlinks=False)
        return {"status": "imported", "counts": manifest["counts"], "path": str(destination)}
    except LegacyImportError:
        raise
    except Exception:
        raise LegacyImportError(
            "Import failed validation or publication; no incomplete bundle was published."
        ) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--enable-owner", action="store_true", help="Explicitly enable the target principal")
    args = parser.parse_args(argv)
    try:
        result = import_legacy_archive(
            args.source,
            args.destination,
            expected_sha256=args.expected_sha256,
            owner_id=args.owner_id,
            owner_email=args.owner_email,
            owner_disabled=not args.enable_owner,
        )
    except LegacyImportError as error:
        print(f"Import refused: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
