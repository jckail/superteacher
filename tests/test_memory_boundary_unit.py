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

    def test_partial_erasure_is_not_replayed_and_logs_no_provider_details(self):
        for errors, count in [([{"error": "private-provider-body", "id": "private-id"}], 1), ([], 1), ([], 0)]:
            with self.subTest(errors=bool(errors), count=count):
                delete = MagicMock(return_value=SimpleNamespace(count=count, errors=errors))
                listing = MagicMock(
                    return_value=SimpleNamespace(documents=[SimpleNamespace(id="a"), SimpleNamespace(id="b")])
                )
                self.memory._client = MagicMock(
                    return_value=SimpleNamespace(list=listing, documents=SimpleNamespace(delete=delete))
                )
                ns = self.memory.namespace("fixture")
                self.memory._prepared.add(ns)
                self.memory._profile_cache[ns] = (0, ["cached"])
                with self.assertLogs(self.memory.log, level="WARNING") as logs:
                    asyncio.run(self.memory.forget_user("fixture"))
                self.assertEqual(delete.call_count, 1)
                self.assertEqual(listing.call_count, 1)
                self.assertEqual(delete.call_args.args, (ns,))
                self.assertEqual(
                    listing.call_args.kwargs["filter"],
                    {"field": "source", "operator": "eq", "value": self.memory.SOURCE},
                )
                self.assertNotIn(ns, self.memory._prepared)
                self.assertNotIn(ns, self.memory._profile_cache)
                self.assertIn("MemoryErasureIncompleteError", " ".join(logs.output))
                self.assertNotIn("private-provider-body", " ".join(logs.output))
                self.assertNotIn("private-id", " ".join(logs.output))

    def test_erasure_verifies_empty_scope_after_the_last_allowed_batch(self):
        for total in [205, 5000, 5001]:
            with self.subTest(total=total):
                stored = [str(i) for i in range(total)]
                batches = []

                def listing(ns, kind, _stored=stored, **kwargs):
                    self.assertEqual(ns, self.memory.namespace("fixture"))
                    self.assertEqual(kind, "documents")
                    self.assertEqual(kwargs["limit"], 100)
                    return SimpleNamespace(documents=[SimpleNamespace(id=i) for i in _stored[:100]])

                def delete(ns, *, ids, _stored=stored, _batches=batches):
                    _batches.append(list(ids))
                    del _stored[: len(ids)]
                    return SimpleNamespace(count=len(ids), errors=[])

                self.memory._client = MagicMock(
                    return_value=SimpleNamespace(list=listing, documents=SimpleNamespace(delete=delete))
                )
                if total > 5000:
                    with self.assertRaises(self.memory.MemoryErasureIncompleteError):
                        self.memory._forget_user_sync("fixture")
                    self.assertEqual(stored, ["5000"])
                    self.assertEqual(len(batches), 50)
                else:
                    self.assertEqual(self.memory._forget_user_sync("fixture"), total)
                    self.assertEqual(stored, [])
                self.assertTrue(all(0 < len(batch) <= 100 for batch in batches))
