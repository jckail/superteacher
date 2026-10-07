import asyncio
import json
from contextlib import contextmanager
from threading import get_ident
from types import SimpleNamespace as NS

import pytest

from superteacher import agent_harness, ai_tools
from tests.ai_fakes import FakeAI, FakeStream, end_turn, text_block, tool_block, tool_turn

SYSTEM = [
    {"type": "text", "text": "instructions"},
    {"type": "text", "text": "roster", "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": "focus"},
]


def harness(client, session_factory=None, **kwargs):
    return agent_harness.run_streamed(
        client,
        [{"role": "user", "content": "who needs support?"}],
        SYSTEM,
        session_factory,
        "synthetic-owner",
        kwargs.pop("max_iterations", 3),
        "configured-sonnet",
        1024,
        **kwargs,
    )


def collect(gen):
    async def run():
        return [event async for event in gen]

    return asyncio.run(run())


@contextmanager
def fake_session():
    yield "synthetic-db"


def test_actual_runner_streams_and_preserves_provider_settings():
    client = FakeAI([end_turn("First", " answer")])
    assert collect(harness(client, request_options={"thinking": {"type": "between_tools"}})) == [
        {"type": "delta", "text": "First"},
        {"type": "delta", "text": " answer"},
    ]
    request = client.stream_calls[0]
    assert request["system"] == SYSTEM
    assert request["model"] == "configured-sonnet"
    assert request["max_tokens"] == 1024
    assert request["thinking"] == {"type": "between_tools"}
    assert "tools" not in request
    assert client.streams[0].closed
    assert client.close_calls == 0  # The application owns the transport client.


def test_actual_runner_tools_preserve_thinking_group_results_and_owner(monkeypatch):
    calls = []
    main_thread = get_ident()

    def execute(db, name, args, owner_id):
        calls.append((db, name, args, owner_id, get_ident()))
        return json.dumps({"matches": []})

    monkeypatch.setattr(ai_tools, "execute", execute)
    blocks = [
        NS(type="thinking", thinking="private reasoning", signature="synthetic-signature"),
        NS(type="redacted_thinking", data="synthetic-redacted"),
        text_block("Checking. "),
        tool_block("a", "class_stats", {}),
        tool_block("b", "find_students", {"risk": "unknown"}),
    ]
    client = FakeAI([FakeStream(["Checking. "], "tool_use", blocks), end_turn("Done")])
    events = collect(harness(client, fake_session))
    assert [event["name"] for event in events if event["type"] == "tool"] == ["class_stats", "find_students"]
    assert "".join(event["text"] for event in events if event["type"] == "delta") == "Checking. Done"
    second = client.stream_calls[1]["messages"]
    assert second[-2]["content"] == [dict(vars(block)) for block in blocks]
    assert [item["tool_use_id"] for item in second[-1]["content"]] == ["a", "b"]
    assert all(call[3] == "synthetic-owner" and call[4] != main_thread for call in calls)
    assert {tool["name"] for tool in client.stream_calls[0]["tools"]} == ai_tools.TOOL_NAMES


def test_actual_runner_tool_validation_and_unknown_tool_recover(session_factory):
    client = FakeAI(
        [
            tool_turn("a", "find_students", {"limit": "many"}),
            tool_turn("b", "drop_database", {}),
            end_turn("Recovered"),
        ]
    )
    events = collect(harness(client, session_factory))
    bad_args = client.stream_calls[1]["messages"][-1]["content"][0]
    unknown = client.stream_calls[2]["messages"][-1]["content"][0]
    assert bad_args["is_error"] and "Invalid arguments" in bad_args["content"]
    assert unknown["is_error"] and "Unknown tool" in unknown["content"]
    assert events[-1] == {"type": "delta", "text": "Recovered"}
    assert {event["name"] for event in events if event["type"] == "tool"} == {"find_students", "drop_database"}


def test_actual_runner_limit_caps_provider_calls(monkeypatch):
    monkeypatch.setattr(ai_tools, "execute", lambda *args, **kwargs: "{}")
    client = FakeAI([tool_turn(str(i), "class_stats", {}) for i in range(5)])
    events = collect(harness(client, fake_session, max_iterations=2))
    assert len(client.stream_calls) == 2
    assert events[-1] == {"type": "delta", "text": agent_harness.LIMIT_TEXT}


@pytest.mark.parametrize(
    "reason,suffix",
    [
        ("refusal", agent_harness.REFUSAL_TEXT),
        ("max_tokens", agent_harness.TRUNCATED_TEXT),
        ("pause_turn", agent_harness.LIMIT_TEXT),
    ],
)
def test_actual_runner_terminal_reasons_do_not_retry(reason, suffix):
    client = FakeAI([FakeStream(["partial"], reason, [text_block("partial")])])
    events = collect(harness(client))
    assert len(client.stream_calls) == 1
    assert events[-1] == {"type": "delta", "text": suffix}


def test_truncation_does_not_execute_incomplete_tools(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Truncated provider calls must not execute tools")

    monkeypatch.setattr(ai_tools, "execute", forbidden)
    client = FakeAI([FakeStream([], "max_tokens", [tool_block("a", "class_stats", {})])])
    assert collect(harness(client, fake_session)) == [{"type": "delta", "text": agent_harness.TRUNCATED_TEXT}]


def test_actual_runner_cancellation_closes_pending_upstream():
    entered = asyncio.Event()

    class WaitingStream(FakeStream):
        @property
        def text_stream(self):
            async def generate():
                yield "first"
                entered.set()
                await asyncio.Event().wait()

            return generate()

    stream = WaitingStream([], "end_turn", [])
    client = FakeAI([stream])

    async def run():
        events = harness(client)
        assert await events.__anext__() == {"type": "delta", "text": "first"}
        await asyncio.wait_for(events.aclose(), timeout=1)

    asyncio.run(run())
    assert stream.closed
    assert client.close_calls == 0


def test_provider_failure_propagates_and_closes_transport_stream():
    error = OSError("synthetic provider failure")
    client = FakeAI([FakeStream([], "end_turn", [], raises=error)])
    with pytest.raises(OSError, match="synthetic provider failure"):
        collect(harness(client))
    assert client.streams[0].closed


def test_cache_usage_is_included_without_losing_counters():
    final = NS(usage=NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=30, cache_creation_input_tokens=20))
    usage = agent_harness.AnthropicModel._usage(final)
    assert usage.input_tokens == 60 and usage.total_tokens == 65
    assert usage.input_tokens_details.cached_tokens == 30
    assert usage.input_tokens_details.cache_write_tokens == 20


def test_nonstream_model_response_uses_same_provider_contract():
    from agents import ModelSettings
    from agents.models.interface import ModelTracing

    client = FakeAI(creates=["answer"])
    model = agent_harness.AnthropicModel(
        client,
        [{"role": "user", "content": "hello"}],
        SYSTEM,
        "configured-sonnet",
        1024,
        tools_enabled=False,
    )
    response = asyncio.run(
        model.get_response(
            None,
            [],
            ModelSettings(),
            [],
            None,
            [],
            ModelTracing.DISABLED,
        )
    )
    assert response.output[0].content[0].text == "answer"
    assert response.usage.requests == 1
    assert client.create_calls[0]["system"] == SYSTEM


def test_provider_error_does_not_use_runner_retries():
    import anthropic

    from tests.ai_fakes import api_error

    client = FakeAI(
        [FakeStream([], "end_turn", [], raises=api_error(anthropic.RateLimitError, 429)), end_turn("retry")]
    )
    with pytest.raises(anthropic.RateLimitError):
        collect(harness(client))
    assert len(client.stream_calls) == 1


def test_injected_tool_runner_preserves_lookup_error_contract():
    calls = []

    async def execute(factory, owner, block):
        calls.append((factory, owner, block.id, block.name, block.input))
        return {"type": "tool_result", "tool_use_id": block.id, "content": "safe error", "is_error": True}

    client = FakeAI([tool_turn("a", "class_stats", {}), end_turn("done")])
    collect(harness(client, fake_session, tool_runner=execute))
    assert calls == [(fake_session, "synthetic-owner", "a", "class_stats", {})]
    assert client.stream_calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_sdk_multiple_lookups_are_serialized_before_database_access():
    active = 0
    maximum = 0
    calls = []

    async def execute(factory, owner, block):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        calls.append(block.name)
        active -= 1
        return {"content": "{}"}

    client = FakeAI(
        [
            FakeStream(
                [],
                "tool_use",
                [tool_block("a", "class_stats", {}), tool_block("b", "get_student", {"student_id": "synthetic"})],
            ),
            end_turn("done"),
        ]
    )
    collect(harness(client, fake_session, tool_runner=execute))
    assert maximum == 1
    assert calls == ["class_stats", "get_student"]
