"""Verify synthetic candidate writes, then reuse the private receipt after an isolated restore."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx

SERVICE = "superteacher-overhaul-staging"
POINTS = 20.123456789


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def candidate_url(value: str, *, expected_tag: str | None = None) -> str:
    prefix = SERVICE
    if expected_tag is not None:
        require(
            isinstance(expected_tag, str)
            and re.fullmatch(r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", expected_tag) is not None
            and "---" not in expected_tag,
            "Expected tag must be an unambiguous lowercase DNS label",
        )
        # Selecting a tag must reject the base URL: it serves the old revision.
        prefix = f"{expected_tag}---{SERVICE}"
    url = httpx.URL(value)
    require(
        url.scheme == "https"
        and not url.userinfo
        and url.port in (None, 443)
        and url.path == "/"
        and not url.query
        and not url.fragment
        and re.fullmatch(rf"{re.escape(prefix)}-[a-z0-9-]+(?:\.[a-z0-9-]+)?\.run\.app", url.host or "") is not None,
        "Only the explicitly isolated superteacher-overhaul-staging Cloud Run service is allowed",
    )
    return str(url).rstrip("/")


def private_json(path: Path) -> dict:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor) as stream:
        metadata = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(metadata.st_mode)
            and stat.S_IMODE(metadata.st_mode) == 0o600
            and metadata.st_uid == os.getuid(),
            "Private files must be owned by the caller with mode 0600",
        )
        value = json.load(stream)
    require(isinstance(value, dict), "Private file must contain a JSON object")
    return value


class Receipt:
    def __init__(self, path: Path, data: dict):
        # Refuse to overwrite previous recovery evidence, including symlinks.
        self.descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.fchmod(self.descriptor, 0o600)
        self.data = data
        self.save()

    def save(self) -> None:
        encoded = (json.dumps(self.data, indent=2) + "\n").encode()
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        os.ftruncate(self.descriptor, 0)
        view = memoryview(encoded)
        while view:
            view = view[os.write(self.descriptor, view) :]
        os.fsync(self.descriptor)

    def record(self, **values) -> None:
        self.data.update(values)
        self.save()

    def close(self) -> None:
        os.close(self.descriptor)


def request(client: httpx.Client, method: str, path: str, status: int = 200, **kwargs):
    response = client.request(method, path, **kwargs)
    require(response.status_code == status, f"Unexpected HTTP status for {method} {path}")
    return response.json() if response.content else None


def verify_records(client: httpx.Client, record: dict) -> None:
    student_id, source, target = record["student_id"], record["source_section_id"], record["target_section_id"]
    student = request(client, "GET", f"/api/students/{student_id}")
    require(student["section_id"] == target and student["name"] == record["student_name"], "Transfer did not persist")
    require(any(n["id"] == record["note_id"] and n["body"] == record["note"] for n in student["notes"]), "Note lost")
    require(
        any(a["day"] == record["day"] and a["status"] == "present" for a in student["attendance"]), "Attendance lost"
    )
    require(student["scores"] == [] and student["average"] is None, "Old-section grades leaked into active grades")
    history = request(client, "GET", f"/api/students/{student_id}/grade-history")
    require(history["active_section_id"] == target, "History active section mismatch")
    old_section = next(s for s in history["sections"] if s["section_id"] == source)
    score = next(s for s in old_section["scores"] if s["assessment_id"] == record["assessment_id"])
    require(score["points"] == POINTS and score["max_points"] == 10, "Raw extra-credit score changed")
    require(math.isclose(score["pct"], POINTS / 10 * 100, rel_tol=0, abs_tol=1e-9), "Historical percent changed")
    old_book = request(client, "GET", f"/api/sections/{source}/gradebook")
    require(all(r["student_id"] != student_id for r in old_book["rows"]), "Transferred student remains in old roster")
    new_book = request(client, "GET", f"/api/sections/{target}/gradebook")
    require(any(r["student_id"] == student_id for r in new_book["rows"]), "Transferred student missing from new roster")
    overview = request(client, "GET", "/api/overview", params={"section_id": target})
    require(overview["students"] == 1 and overview["average"] is None, "Active-section overview mismatch")
    courses = request(client, "GET", "/api/courses")
    course = next(c for c in courses if c["id"] == record["course_id"])
    require(course["name"] == record["course_name"], "Course metadata changed")
    require({source, target} <= {s["id"] for s in course["sections"]}, "Course sections lost")


def create_records(client: httpx.Client, receipt: Receipt, day: str) -> None:
    suffix = uuid4().hex[:12]
    course_name = f"Synthetic candidate {suffix}"
    course = request(
        client, "POST", "/api/courses", 201, json={"name": course_name, "initial_section_name": "Before transfer"}
    )
    receipt.record(course_id=course["id"], course_name=course_name)
    require(len(course["sections"]) == 1, "Atomic course creation must create exactly one initial section")
    source = course["sections"][0]["id"]
    require(course["sections"][0]["name"] == "Before transfer", "Initial section name changed")
    receipt.record(source_section_id=source, day=day)
    student = request(
        client,
        "POST",
        "/api/students",
        201,
        json={"name": f"Synthetic Learner {suffix}", "grade_level": 10, "section_id": source},
    )
    receipt.record(student_id=student["id"])
    title = f"Synthetic precision {suffix}"
    book = request(
        client,
        "POST",
        f"/api/sections/{source}/assessments",
        201,
        json={"title": title, "kind": "test", "max_points": 10, "due_date": day},
    )
    assessment = next(a for a in book["assessments"] if a["title"] == title)
    receipt.record(assessment_id=assessment["id"], points=POINTS, max_points=10)
    book = request(
        client,
        "PUT",
        f"/api/assessments/{assessment['id']}/scores",
        json={"scores": [{"student_id": student["id"], "points": POINTS}]},
    )
    row = next(r for r in book["rows"] if r["student_id"] == student["id"])
    require(row["points"][assessment["id"]] == POINTS, "Score was capped or rounded on write")
    note_text = f"Synthetic durability note {suffix}; no real student information."
    note = request(client, "POST", f"/api/students/{student['id']}/notes", 201, json={"body": note_text})
    receipt.record(note_id=note["id"], note=note_text)
    request(
        client,
        "PUT",
        f"/api/sections/{source}/attendance",
        json={"day": day, "marks": [{"student_id": student["id"], "status": "present"}]},
    )
    target = request(client, "POST", "/api/sections", 201, json={"course_id": course["id"], "name": "After transfer"})
    receipt.record(target_section_id=target["id"])
    student_name = f"Synthetic Transferred {suffix}"
    request(client, "PATCH", f"/api/students/{student['id']}", json={"section_id": target["id"], "name": student_name})
    receipt.record(student_name=student_name, stage="records_created")
    verify_records(client, receipt.data)
    receipt.record(stage="writes_verified")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--expected-tag", help="Exact Cloud Run traffic tag; rejects the base service URL and other tags"
    )
    parser.add_argument(
        "--credentials", required=True, type=Path, help="Caller-owned 0600 JSON file containing password"
    )
    parser.add_argument(
        "--receipt", required=True, type=Path, help="New private receipt, or existing receipt in verify mode"
    )
    parser.add_argument(
        "--isolated-candidate",
        action="store_true",
        required=True,
        help="Acknowledge this uses isolated staging storage",
    )
    parser.add_argument(
        "--verify-receipt", action="store_true", help="Read previously created records; do not create more"
    )
    parser.add_argument("--expected-timezone", default="UTC")
    args = parser.parse_args()
    receipt = None
    stage = "validate_inputs"
    try:
        url = candidate_url(args.url, expected_tag=args.expected_tag)
        credentials = private_json(args.credentials)
        require(
            isinstance(credentials.get("password"), str) and bool(credentials["password"]), "Missing private password"
        )
        require(
            "url" not in credentials or candidate_url(credentials["url"], expected_tag=args.expected_tag) == url,
            "Credential URL mismatch",
        )
        require(
            "release" not in credentials or credentials["release"] == args.expected_version,
            "Credential release mismatch",
        )
        record = private_json(args.receipt) if args.verify_receipt else None
        if record is not None:
            require(record["url"] == url and record["version"] == args.expected_version, "Receipt candidate mismatch")
            require(record["stage"] in {"writes_verified", "smoke_passed"}, "Receipt has incomplete writes")
        else:
            receipt = Receipt(args.receipt, {"url": url, "version": args.expected_version, "stage": "started"})
        with httpx.Client(
            base_url=url,
            timeout=30,
            follow_redirects=False,
            trust_env=False,
            headers={"X-Requested-With": "candidate-verification", "Origin": url},
        ) as client:
            stage = "public_probes"
            require(request(client, "GET", "/api/health")["status"] == "healthy", "Candidate health failed")
            require(request(client, "GET", "/api/ready")["status"] == "ready", "Candidate readiness failed")
            require(
                request(client, "GET", "/api/version")["version"] == args.expected_version, "Candidate version mismatch"
            )
            spa = client.get("/")
            require(spa.status_code == 200 and '<div id="root">' in spa.text, "Candidate SPA missing")
            request(client, "GET", "/api/overview", 401)
            request(client, "GET", "/api/calendar", 401)
            stage = "authenticate"
            request(client, "POST", "/api/auth/login", json={"password": credentials["password"]})
            verified = False
            try:
                require(request(client, "GET", "/api/auth/me")["authenticated"] is True, "Login did not authenticate")
                calendar = request(client, "GET", "/api/calendar")
                require(calendar["timezone"] == args.expected_timezone, "School timezone mismatch")
                date.fromisoformat(calendar["today"])
                stage = "verify_restored_records" if record is not None else "create_synthetic_records"
                if record is not None:
                    verify_records(client, record)
                else:
                    create_records(client, receipt, calendar["today"])
                require(request(client, "GET", "/api/ready")["status"] == "ready", "Post-write readiness failed")
                verified = True
            finally:
                if verified:
                    stage = "logout"
                request(client, "POST", "/api/auth/logout")
                request(client, "GET", "/api/overview", 401)
                request(client, "GET", "/api/calendar", 401)
            if receipt is not None:
                receipt.record(stage="smoke_passed")
        print(
            json.dumps(
                {
                    "result": "passed",
                    "mode": "restore_readback" if args.verify_receipt else "synthetic_writes",
                    "version": args.expected_version,
                    "receipt": str(args.receipt),
                    "records_preserved": True,
                }
            )
        )
        return 0
    except (ValueError, KeyError, TypeError, StopIteration, OSError, httpx.HTTPError) as error:
        # Never log request/response bodies, credentials, cookies or exception messages.
        print(
            f"Candidate verification failed at {stage} ({type(error).__name__}); preserve receipt for investigation.",
            file=sys.stderr,
        )
        return 1
    finally:
        if receipt is not None:
            receipt.close()


if __name__ == "__main__":
    raise SystemExit(main())
