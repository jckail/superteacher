"""Roster server order: Python lower search, raw strings, nulls last, raw name/id ties.

Cursors are signed, readable live-read continuation keys, not snapshot or access grants.
"""

import math
from dataclasses import dataclass
from datetime import date

from itsdangerous import BadData, URLSafeSerializer

RISK_RANK = {"at_risk": 0, "watch": 1, "unknown": 2, "on_track": 3}
NUMERIC_SORTS = {"average", "trend", "attendance_rate", "homework_rate"}
MAX_CURSOR = 8192


@dataclass(frozen=True)
class PageQuery:
    q: str = ""
    course_id: str | None = None
    section_id: str | None = None
    risk: str | None = None
    sort: str = "risk"
    direction: str = "asc"
    limit: int = 50

    def identity(self):
        return [
            self.q.strip().lower(),
            self.course_id,
            self.section_id,
            self.risk,
            self.sort,
            self.direction,
            self.limit,
        ]


def comparison_key(student, metric, sort):
    if sort == "name":
        value = student.name.lower()
    elif sort == "section":
        value = student.section.course.name + " " + student.section.name
    elif sort == "risk":
        value = RISK_RANK[metric.risk]
    else:
        value = getattr(metric, sort)
    return (int(value is None), value, student.name, student.id)


def compare(a, b, direction):
    if a[0] != b[0]:
        return (a[0] > b[0]) - (a[0] < b[0])
    if not a[0] and a[1] != b[1]:
        result = (a[1] > b[1]) - (a[1] < b[1])
        return -result if direction == "desc" else result
    return (a[2:] > b[2:]) - (a[2:] < b[2:])


def encode_cursor(serializer: URLSafeSerializer, owner, query, as_of, key):
    return serializer.dumps(
        {
            "v": 1,
            "purpose": "roster-page",
            "owner": owner,
            "query": query.identity(),
            "as_of": as_of.isoformat(),
            "key": list(key),
        }
    )


def decode_cursor(serializer: URLSafeSerializer, token, owner, query):
    """Strict bounded validation; callers expose only a generic continuation error."""
    try:
        if type(token) is not str or not 1 <= len(token) <= MAX_CURSOR or not token.isascii():
            raise ValueError
        payload = serializer.loads(token)
        if type(payload) is not dict or set(payload) != {"v", "purpose", "owner", "query", "as_of", "key"}:
            raise ValueError
        if type(payload["v"]) is not int or payload["v"] != 1 or payload["purpose"] != "roster-page":
            raise ValueError
        if type(payload["owner"]) is not str or payload["owner"] != owner:
            raise ValueError
        if type(payload["query"]) is not list or payload["query"] != query.identity():
            raise ValueError
        # Equality alone accepts bool == int. Enforce each identity field's exact type.
        if any(type(a) is not type(b) for a, b in zip(payload["query"], query.identity(), strict=True)):
            raise ValueError
        stamp = payload["as_of"]
        if type(stamp) is not str or len(stamp) != 10:
            raise ValueError
        as_of = date.fromisoformat(stamp)
        if as_of.isoformat() != stamp:
            raise ValueError
        key = payload["key"]
        if type(key) is not list or len(key) != 4 or type(key[0]) is not int or key[0] not in (0, 1):
            raise ValueError
        if (
            type(key[2]) is not str
            or not 1 <= len(key[2]) <= 120
            or type(key[3]) is not str
            or not 1 <= len(key[3]) <= 64
        ):
            raise ValueError
        value = key[1]
        if key[0]:
            if query.sort not in NUMERIC_SORTS or value is not None:
                raise ValueError
        elif query.sort in NUMERIC_SORTS:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError
        elif query.sort == "risk":
            if type(value) is not int or value not in RISK_RANK.values():
                raise ValueError
        elif type(value) is not str or len(value) > 241:
            raise ValueError
        return as_of, tuple(key)
    except (BadData, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Invalid continuation") from exc
