import asyncio
import json
import re
import time
from types import SimpleNamespace as NS

import pytest

from superteacher import ai, memory
from superteacher.config import get_settings
from tests.ai_fakes import FakeAI, end_turn


class FakeSM:
    """Records every SDK call; mirrors the v5 client surface used by superteacher.memory."""

    def __init__(self, fail=False):
        self.fail, self.adds, self.searches, self.profile_calls = fail, [], [], []
        self.ns_updates, self.bucket_sets, self.deletes, self.lists = [], [], [], []
        self.namespaces = NS(update=self._ns_update)
        self.profiles = NS(set_buckets=self._set_buckets)
        self.documents = NS(delete=self._delete)
        self.stored = ["d1", "d2"]

    def _ns_update(self, ns, **kw):
        self.ns_updates.append((ns, kw))

    def _set_buckets(self, ns, **kw):
        self.bucket_sets.append((ns, kw))

    def _delete(self, ns, **kw):
        self.deletes.append((ns, kw))
        self.stored = [i for i in self.stored if i not in kw["ids"]]
        return NS(count=len(kw["ids"]), errors=[])

    def list(self, ns, kind, **kw):
        self.lists.append((ns, kind, kw))
        return NS(documents=[NS(id=i) for i in self.stored])

    def profile(self, ns, **kw):
        self.profile_calls.append((ns, kw))
        if self.fail:
            raise RuntimeError("boom")
        return NS(
            profile=NS(
                static=[NS(memory="Teaches 7th grade math")],
                dynamic=[NS(memory="Planning fractions unit")],
                buckets={"teaching_style": [NS(memory="Likes exit tickets")]},
            )
        )

    def search(self, ns, **kw):
        self.searches.append((ns, kw))
        if self.fail:
            raise RuntimeError("boom")
        return NS(results=[NS(memory="Prefers short answers")])

    def add(self, ns, **kw):
        if self.fail:
            raise RuntimeError("boom")
        self.adds.append((ns, kw))


@pytest.fixture
def sm(monkeypatch):
    fake = FakeSM()
    memory._prepared.clear()
    memory._profile_cache.clear()
    s = get_settings()
    monkeypatch.setattr(s, "supermemory_enabled", True)
    monkeypatch.setattr(s, "supermemory_api_key", "test-key")
    monkeypatch.setattr(memory, "_client", lambda: fake)
    return fake


def test_namespace_is_valid_and_bounded():
    ns = memory.namespace("abc/123 x" * 30)
    assert re.fullmatch(r"[a-zA-Z0-9_:-]+", ns) and len(ns) <= 100
    assert memory.namespace("u1") == "superteacher:teacher-u1"


def test_disabled_by_default_and_in_public_demo(monkeypatch):
    assert not memory.enabled()
    s = get_settings()
    monkeypatch.setattr(s, "supermemory_enabled", True)
    monkeypatch.setattr(s, "supermemory_api_key", "k")
    assert memory.enabled()
    monkeypatch.setattr(s, "public_demo", True)
    assert not memory.enabled()


def test_sanitize_redacts_names_and_caps_length():
    out = memory.sanitize_summary(
        "Ada Lovelace is failing; ask ada about Lovelace's quiz. " + "x" * 900, ["Ada Lovelace"]
    )
    assert "Ada" not in out and "Lovelace" not in out and "[student]" in out
    assert len(out) <= memory.MAX_SUMMARY_CHARS


def test_recall_builds_block(sm):
    out = asyncio.run(memory.recall("u1", "fractions?", []))
    assert "Teaches 7th grade math" in out and "Prefers short answers" in out
    assert [c[0] for c in sm.profile_calls] == ["superteacher:teacher-u1"] and sm.searches[0][1][
        "search_mode"
    ] == "memories"


def test_recall_and_remember_fail_open(sm):
    sm.fail = True
    assert asyncio.run(memory.recall("u1", "q", [])) == ""
    asyncio.run(memory.remember("u1", "s", "hi", "reply", []))  # must not raise


def test_remember_sends_only_message_and_sanitized_summary(sm):
    asyncio.run(memory.remember("u1", "chat-1", "How is Ada doing?", "Ada Lovelace has 41%.", ["Ada Lovelace"]))
    ns, kw = sm.adds[0]
    assert ns == "superteacher:teacher-u1" and kw["id"] == "chat-1" and kw["task_type"] == "memory"
    assert "Lovelace" not in kw["content"] and "Ada" not in kw["content"]
    assert "How is [student] doing?" in kw["content"]


def test_recall_redacts_names_and_requires_roster(sm):
    assert asyncio.run(memory.recall("u1", "Ada?")) == ""
    assert sm.searches == [] and sm.profile_calls == []
    asyncio.run(memory.recall("u1", "How is Li doing?", ["Li Wu"]))
    assert sm.searches[0][1]["query"] == "How is [student] doing?"


def test_recall_uses_v5_search_options_and_typed_filter(sm):
    out = asyncio.run(memory.recall("u1", "fractions?", []))
    kw = sm.searches[0][1]
    assert kw["search_mode"] == "memories" and kw["rerank"] == "order" and kw["rewrite_query"] is True
    assert kw["limit"] == 5 and kw["threshold"] == 0.4 and kw["timeout"] == memory.CALL_TIMEOUT
    flt = {"field": "source", "operator": "eq", "value": memory.SOURCE}
    assert kw["filter"] == flt and sm.profile_calls[0][1]["filter"] == flt
    assert "teaching style: Likes exit tickets" in out  # profile buckets are surfaced


def test_profile_is_cached_between_turns(sm):
    asyncio.run(memory.recall("u1", "one", []))
    out = asyncio.run(memory.recall("u1", "two", []))
    assert len(sm.profile_calls) == 1 and len(sm.searches) == 2
    assert "Teaches 7th grade math" in out


def test_recall_is_bounded_and_runs_concurrently(sm, monkeypatch):
    monkeypatch.setattr(memory, "RECALL_BUDGET", 0.2)
    started = []

    def slow_search(ns, **kw):
        started.append("search")
        time.sleep(1.0)
        return NS(results=[])

    sm.search = slow_search

    async def timed():
        t0 = time.monotonic()
        return await memory.recall("u1", "q", []), time.monotonic() - t0

    out, elapsed = asyncio.run(timed())  # (asyncio.run itself then waits for the sleeping worker thread)
    assert elapsed < 0.9  # the budget, not the slow call, bounds the wait
    assert "Teaches 7th grade math" in out and started == ["search"]  # fast profile still used


def test_remember_sends_rich_metadata_group_and_context(sm):
    asyncio.run(memory.remember("u1", "chat-1", "plan fractions", "ok", []))
    _ns, kw = sm.adds[0]
    md = kw["metadata"]
    assert md["source"] == memory.SOURCE and md["kind"] == "chat-turn" and md["thread"] == "chat-1"
    assert md["user"] == "u1" and md["date"] == kw["date"] and kw["date"].endswith("+00:00")
    assert kw["group"] == {"source": memory.SOURCE} and "dreaming" not in kw
    assert 0 < len(kw["supporting_context"]) <= 1500


def test_namespace_settings_pushed_once_per_namespace(sm):
    for i in range(3):
        asyncio.run(memory.remember("u1", f"c{i}", "hi", "ok", []))
    asyncio.run(memory.remember("u2", "c9", "hi", "ok", []))
    assert [n for n, _ in sm.ns_updates] == ["superteacher:teacher-u1", "superteacher:teacher-u2"]
    ctx = sm.ns_updates[0][1]["supporting_context"]
    assert len(ctx) <= 1500 and "individual students" in ctx
    assert set(sm.bucket_sets[0][1]["buckets"]) == {"teaching_style", "preferences", "curriculum"}


def test_namespace_setup_failure_is_swallowed_and_retried(sm):
    def boom(ns, **kw):
        raise RuntimeError("nope")

    sm.namespaces = NS(update=boom)
    asyncio.run(memory.remember("u1", "c1", "hi", "ok", []))
    assert len(sm.adds) == 1 and not memory._prepared  # add succeeded, setup retried next time


def test_forget_user_deletes_documents_in_batches(sm):
    sm.stored = [f"d{i}" for i in range(3)]
    asyncio.run(memory.forget_user("u1"))
    assert sm.deletes == [("superteacher:teacher-u1", {"ids": ["d0", "d1", "d2"]})]
    assert sm.lists[0][1] == "documents" and sm.lists[0][2]["filter"]["value"] == memory.SOURCE


def test_forget_user_fail_open_and_disabled(sm, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("x")

    sm.list = boom
    asyncio.run(memory.forget_user("u1"))  # must not raise
    monkeypatch.setattr(get_settings(), "supermemory_enabled", False)
    asyncio.run(memory.forget_user("u1"))


def test_chat_ws_injects_memory_and_stores_exchange(client, session_factory, sm, monkeypatch):
    with session_factory() as db:
        names = memory.student_names(db, "x")
    assert names == []  # no data for an unknown owner
    fake = FakeAI([end_turn("Hello", " there")])
    monkeypatch.setattr(ai, "client", lambda: fake)
    with client.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "plan my fractions unit"})
        while ws.receive_json()["type"] not in ("done", "error"):
            pass
    system = json.dumps(fake.stream_calls[0]["system"])
    assert "Prefers short answers" in system and "Teaches 7th grade math" in system
    for _ in range(50):  # the add is fire-and-forget
        if sm.adds:
            break
        time.sleep(0.05)
    assert sm.adds and "plan my fractions unit" in sm.adds[0][1]["content"]
    assert sm.adds[0][0].startswith("superteacher:teacher-")


def test_chat_ws_works_when_memory_errors(client, sm, monkeypatch):
    sm.fail = True
    fake = FakeAI([end_turn("ok")])
    monkeypatch.setattr(ai, "client", lambda: fake)
    with client.websocket_connect("/api/chat/ws") as ws:
        ws.send_json({"content": "hi"})
        types = []
        while (t := ws.receive_json()["type"]) not in ("done", "error"):
            types.append(t)
        assert t == "done"


def test_account_deletion_forgets_stored_chat_memory(tmp_path, sm):
    from tests.acct_util import H, build, sign_in

    with build(tmp_path) as c:
        sign_in(c, tmp_path, "gone@example.com")
        assert c.request("DELETE", "/api/account", json={"email": "gone@example.com"}, headers=H).status_code == 204
    assert len(sm.deletes) == 1 and sm.deletes[0][1] == {"ids": ["d1", "d2"]}
    assert sm.deletes[0][0].startswith("superteacher:teacher-")
