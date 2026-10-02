"""Synthetic Insight provenance; provider calls are fake and native execution needs CI."""

import asyncio
import json
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from superteacher import ai, metrics
from superteacher.models import InsightCache, Student
from tests.ai_fakes import FakeAI

GOOD = json.dumps({"headline": "Recorded advice", "strengths": [], "concerns": [], "actions": []})
DAY = date(2026, 10, 1)


def test_new_ai_and_owned_cache_share_cutoff_timestamp_without_charging_again(seeded, monkeypatch):
    monkeypatch.setattr(metrics, "school_today", lambda: DAY)
    monkeypatch.setattr(ai.get_settings(), "anthropic_api_key", "synthetic-key")
    fake = FakeAI(creates=[GOOD])
    monkeypatch.setattr(ai, "client", lambda: fake)
    charged = []
    with seeded.app.state.session_factory() as db:
        student = db.scalars(select(Student)).first()
        result = asyncio.run(ai.ai_insight(db, student, before_generate=lambda: charged.append(True)))
        assert result.as_of == DAY and result.generated_at.tzinfo is UTC
        assert len(fake.create_calls) == len(charged) == 1
        row = db.get(InsightCache, student.id)
        assert row.created_at.replace(tzinfo=UTC) == result.generated_at
        # SQLite returns native DateTime values naïve; it is a stored UTC instant.
        instant = datetime(2026, 10, 1, 12, 34, 56)
        row.created_at = instant
        db.commit()
        cached = asyncio.run(ai.ai_insight(db, student, before_generate=lambda: charged.append(True)))
        assert cached.generated_at == instant.replace(tzinfo=UTC)
        assert cached.as_of == DAY
        assert len(fake.create_calls) == len(charged) == 1


def test_delayed_generation_preserves_captured_cutoff_and_next_day_misses_cache(seeded, monkeypatch):
    day = DAY
    monkeypatch.setattr(metrics, "school_today", lambda: day)
    monkeypatch.setattr(ai.get_settings(), "anthropic_api_key", "synthetic-key")

    started = asyncio.Event()
    finish = asyncio.Event()

    class Midnight(FakeAI):
        async def create(self, **kwargs):
            if not self.create_calls:
                started.set()
                await finish.wait()
            return await super().create(**kwargs)

    fake = Midnight(creates=[GOOD, GOOD])
    monkeypatch.setattr(ai, "client", lambda: fake)
    with seeded.app.state.session_factory() as db:
        student = db.scalars(select(Student)).first()

        async def check():
            nonlocal day
            pending = asyncio.create_task(ai.ai_insight(db, student))
            await started.wait()
            day = date(2026, 10, 2)
            assert not pending.done()
            finish.set()
            result = await pending
            assert result.as_of == DAY
            next_day = await ai.ai_insight(db, student)
            assert next_day.as_of == day and len(fake.create_calls) == 2

        asyncio.run(check())


@pytest.mark.parametrize("cause", ["no-key", "capacity", "generation-failure", "generation-exception"])
def test_rule_fallback_has_calculation_cutoff_and_no_ai_timestamp(seeded, monkeypatch, cause):
    monkeypatch.setattr(metrics, "school_today", lambda: DAY)
    if cause != "no-key":
        monkeypatch.setattr(ai.get_settings(), "anthropic_api_key", "synthetic-key")
    if cause == "capacity":

        def saturated():
            raise ai.ai_capacity.CapacityError()

        monkeypatch.setattr(ai.ai_capacity, "acquire", saturated)
    if cause in {"generation-failure", "generation-exception"}:

        async def fail(*args):
            if cause == "generation-exception":
                raise RuntimeError("synthetic provider failure")
            return None

        monkeypatch.setattr(ai, "_generate", fail)
    with seeded.app.state.session_factory() as db:
        student = db.scalars(select(Student)).first()
        result = asyncio.run(ai.ai_insight(db, student))
        assert result.source == "rules" and result.as_of == DAY
        assert result.generated_at is None and result.model is None
