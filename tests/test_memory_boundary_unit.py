"""Offline memory boundary checks, runnable with stdlib unittest and no application database."""

import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch


def load_memory():
    settings = SimpleNamespace(supermemory_enabled=True, supermemory_api_key="fixture", public_demo=False)
    config = ModuleType("superteacher.config")
    config.get_settings = lambda: settings
    models = ModuleType("superteacher.models")
    models.Course = models.Section = models.Student = object
    sqlalchemy = ModuleType("sqlalchemy")
    sqlalchemy.select = lambda *args: None
    spec = importlib.util.spec_from_file_location(
        "superteacher.memory_boundary_fixture", Path(__file__).resolve().parents[1] / "superteacher/memory.py"
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        "sys.modules",
        {
            "superteacher.config": config,
            "superteacher.models": models,
            "sqlalchemy": sqlalchemy,
        },
    ):
        spec.loader.exec_module(module)
    return module


class MemoryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.memory = load_memory()
        self.adds, self.queries = [], []
        fake = SimpleNamespace(
            add=lambda ns, **kw: self.adds.append((ns, kw)),
            profile=lambda ns, **kw: SimpleNamespace(profile=SimpleNamespace(static=[], dynamic=[], buckets={})),
            search=lambda ns, **kw: self.queries.append((ns, kw)) or SimpleNamespace(results=[]),
            namespaces=SimpleNamespace(update=lambda *args, **kw: None),
            profiles=SimpleNamespace(set_buckets=lambda *args, **kw: None),
        )
        self.memory._client = lambda: fake

    def test_known_short_and_full_names_redacted_from_both_saved_sides(self):
        asyncio.run(
            self.memory.remember(
                "teacher-fixture",
                "session-fixture",
                "How are Li and Ada doing?",
                "Li Wu and Ada Lovelace need help.",
                ["Li Wu", "Ada Lovelace"],
            )
        )
        ns, body = self.adds[0]
        self.assertEqual(ns, "superteacher:teacher-teacher-fixture")
        for name in ["Li", "Wu", "Ada", "Lovelace"]:
            self.assertNotIn(name, body["content"])
        self.assertIn("How are [student] and [student] doing?", body["content"])

    def test_recall_does_not_send_raw_names_or_query_without_roster(self):
        self.assertEqual(asyncio.run(self.memory.recall("fixture", "Ada?")), "")
        self.assertEqual(self.queries, [])
        asyncio.run(self.memory.recall("fixture", "How is Li?", ["Li Wu"]))
        self.assertEqual(self.queries[0][1]["query"], "How is [student]?")

    def test_redaction_precedes_length_limits(self):
        text = "x " * (self.memory.MAX_USER_CHARS // 2 - 1) + "Lovelace"
        asyncio.run(self.memory.remember("fixture", "session", text, "Ada", ["Ada Lovelace"]))
        content = self.adds[0][1]["content"]
        self.assertNotIn("Love", content)
        self.assertLessEqual(len(self.memory.sanitize_summary("x" * 900, [])), 400)

    def test_incomplete_roster_is_rejected_instead_of_silently_truncated(self):
        self.memory.Student = SimpleNamespace(name="name", section_id="section")
        self.memory.Section = SimpleNamespace(id="section", course_id="course")
        self.memory.Course = SimpleNamespace(id="course", owner_id="owner")
        self.memory.select = MagicMock()
        db = SimpleNamespace(scalars=lambda statement: ["Fixture Student"] * 1001)
        with self.assertRaises(ValueError):
            self.memory.student_names(db, "fixture")
