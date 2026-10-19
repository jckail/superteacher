"""OpenAI Agents SDK orchestration with an owned Anthropic transport.

A model instance belongs to one chat request. Its private provider history retains
signed thinking blocks and cache breakpoints; the Runner owns tool iteration.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from agents import Agent, FunctionTool, ModelSettings, RunConfig, Runner
from agents.exceptions import MaxTurnsExceeded
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.retry import ModelRetrySettings
from agents.usage import Usage
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
    ResponseUsage,
)
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from . import ai_tools

log = logging.getLogger(__name__)
LIMIT_TEXT = "\n\n_(I stopped looking things up after several steps; ask a narrower question.)_"
TRUNCATED_TEXT = "\n\n_(Reply cut short; ask me to continue.)_"
REFUSAL_TEXT = "\n\nI can't help with that request."
_UNKNOWN_TOOL = "unsupported_lookup"


def _block_param(block: Any) -> dict:
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return dict(vars(block))


class AnthropicModel(Model):
    """Adapt one provider call at a time without flattening Anthropic replay data."""

    def __init__(self, client, history, system, model_name, max_output_tokens, *, tools_enabled, request_options=None):
        self.client = client
        self.messages = deepcopy(history)
        self.system = deepcopy(system)
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.tools_enabled = tools_enabled
        self.request_options = deepcopy(request_options or {})
        self.seen_outputs: set[str] = set()
        self.tool_errors: set[str] = set()
        self.tool_names: dict[str, str] = {}

    def _request(self, input, output_schema, handoffs) -> dict:
        if output_schema is not None or handoffs:
            raise ValueError("This classroom model supports text and local lookup tools only")
        results = []
        for item in input if isinstance(input, list) else []:
            if item.get("type") != "function_call_output":
                continue
            call_id = item["call_id"]
            if call_id in self.seen_outputs:
                continue
            self.seen_outputs.add(call_id)
            result = {"type": "tool_result", "tool_use_id": call_id, "content": item["output"]}
            if call_id in self.tool_errors:
                result["is_error"] = True
            results.append(result)
        if results:
            self.messages.append({"role": "user", "content": results})
        request = {
            "model": self.model_name,
            "max_tokens": self.max_output_tokens,
            "system": self.system,
            "messages": self.messages,
        }
        if self.tools_enabled:
            request["tools"] = ai_tools.TOOLS
        request.update(self.request_options)
        return request

    def _items(self, final, message_id: str):
        blocks = [_block_param(block) for block in final.content]
        self.messages.append({"role": "assistant", "content": blocks})
        reason = getattr(final, "stop_reason", "end_turn")
        texts = [block.get("text", "") for block in blocks if block["type"] == "text"]
        suffix = REFUSAL_TEXT if reason == "refusal" else TRUNCATED_TEXT if reason == "max_tokens" else ""
        tool_blocks = [block for block in blocks if block["type"] == "tool_use"]
        if reason == "pause_turn" and not tool_blocks:
            suffix = LIMIT_TEXT
        if suffix:
            texts.append(suffix)
        output = []
        if any(texts) or not tool_blocks:
            output.append(
                ResponseOutputMessage(
                    id=message_id,
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[ResponseOutputText(type="output_text", text="".join(texts), annotations=[])],
                )
            )
        # Truncation/refusal intentionally ends the turn without executing incomplete lookups.
        if reason not in ("max_tokens", "refusal"):
            for block in tool_blocks:
                name, args = block["name"], block["input"]
                self.tool_names[block["id"]] = name
                if name not in ai_tools.TOOL_NAMES:
                    name, args = _UNKNOWN_TOOL, {"name": name, "arguments": args}
                output.append(
                    ResponseFunctionToolCall(
                        id=block["id"],
                        call_id=block["id"],
                        name=name,
                        arguments=json.dumps(args),
                        type="function_call",
                        status="completed",
                    )
                )
        return output, suffix

    @staticmethod
    def _usage(final):
        usage = getattr(final, "usage", None)
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        incoming = (getattr(usage, "input_tokens", 0) or 0) + read + write
        outgoing = getattr(usage, "output_tokens", 0) or 0
        return ResponseUsage(
            input_tokens=incoming,
            output_tokens=outgoing,
            total_tokens=incoming + outgoing,
            input_tokens_details=InputTokensDetails(cached_tokens=read, cache_write_tokens=write),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        )

    async def get_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ) -> ModelResponse:
        final = await self.client.messages.create(**self._request(input, output_schema, handoffs))
        output, _ = self._items(final, "msg_" + uuid4().hex)
        usage = self._usage(final)
        return ModelResponse(
            output=output,
            response_id=None,
            usage=Usage(
                requests=1,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                input_tokens_details=usage.input_tokens_details,
                output_tokens_details=usage.output_tokens_details,
            ),
        )

    async def stream_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    ):
        message_id = "msg_" + uuid4().hex
        sequence = 0
        async with self.client.messages.stream(**self._request(input, output_schema, handoffs)) as stream:
            async for text in stream.text_stream:
                yield ResponseTextDeltaEvent(
                    type="response.output_text.delta",
                    sequence_number=sequence,
                    content_index=0,
                    output_index=0,
                    item_id=message_id,
                    delta=text,
                    logprobs=[],
                )
                sequence += 1
            final = await stream.get_final_message()
        output, suffix = self._items(final, message_id)
        if suffix:
            yield ResponseTextDeltaEvent(
                type="response.output_text.delta",
                sequence_number=sequence,
                content_index=0,
                output_index=0,
                item_id=message_id,
                delta=suffix,
                logprobs=[],
            )
            sequence += 1
        yield ResponseCompletedEvent(
            type="response.completed",
            sequence_number=sequence,
            response=Response(
                id="resp_" + uuid4().hex,
                created_at=time.time(),
                model=self.model_name,
                object="response",
                output=output,
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
                status="completed",
                usage=self._usage(final),
            ),
        )


def _tools(model: AnthropicModel, session_factory, owner_id: str, tool_runner=None) -> list[FunctionTool]:
    # The SDK may schedule returned FunctionTools concurrently even when the model
    # setting discourages parallel calls. Preserve sequential classroom lookups,
    # including session factories backed by a shared SQLite connection.
    lookup_lock = asyncio.Lock()

    def make_invoke(name):
        async def invoke(ctx, arguments):
            async with lookup_lock:
                return await execute(ctx, arguments)

        async def execute(ctx, arguments):
            args = json.loads(arguments)
            lookup_name = name
            if name == _UNKNOWN_TOOL:
                lookup_name, args = args["name"], args["arguments"]

            def work():
                with session_factory() as db:
                    return ai_tools.execute(db, lookup_name, args, owner_id=owner_id)

            try:
                if tool_runner is not None:
                    block = SimpleNamespace(id=ctx.tool_call_id, name=lookup_name, input=args)
                    result = await tool_runner(session_factory, owner_id, block)
                    if result.get("is_error"):
                        model.tool_errors.add(ctx.tool_call_id)
                    return result["content"]
                return await asyncio.to_thread(work)
            except ai_tools.ToolError as exc:
                model.tool_errors.add(ctx.tool_call_id)
                return str(exc)
            except Exception:
                log.exception("tool %s failed", lookup_name)
                model.tool_errors.add(ctx.tool_call_id)
                return "The lookup failed."

        return invoke

    schemas = [
        *ai_tools.TOOLS,
        {
            "name": _UNKNOWN_TOOL,
            "description": "Return an error for an unsupported lookup.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "arguments": {"type": "object"},
                },
            },
        },
    ]
    return [
        FunctionTool(
            name=spec["name"],
            description=spec["description"],
            params_json_schema=deepcopy(spec["input_schema"]),
            strict_json_schema=False,
            on_invoke_tool=make_invoke(spec["name"]),
        )
        for spec in schemas
    ]


async def run_streamed(
    client,
    history,
    system_blocks,
    session_factory,
    owner_id,
    max_iterations,
    model_name,
    max_output_tokens,
    request_options=None,
    tool_runner=None,
) -> AsyncIterator[dict]:
    """Run the SDK harness, preserving the application's public stream contract.

    Provider errors propagate for the caller's friendly error mapping. The caller
    owns the Anthropic client, timeout, capacity lease, and visitor request quota.
    """
    if session_factory is not None and owner_id is None:
        raise ValueError("owner_id is required when tools are enabled")
    model = AnthropicModel(
        client,
        history,
        system_blocks,
        model_name,
        max_output_tokens,
        tools_enabled=session_factory is not None,
        request_options=request_options,
    )
    agent = Agent(
        name="Super Teacher",
        model=model,
        tools=_tools(model, session_factory, owner_id, tool_runner) if session_factory is not None else [],
        model_settings=ModelSettings(
            max_tokens=max_output_tokens, parallel_tool_calls=False, retry=ModelRetrySettings(max_retries=0)
        ),
    )
    result = Runner.run_streamed(
        agent,
        input=deepcopy(history),
        max_turns=max_iterations,
        run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
    )
    events = result.stream_events()
    try:
        async for event in events:
            if event.type == "raw_response_event" and event.data.type == "response.output_text.delta":
                yield {"type": "delta", "text": event.data.delta}
            elif event.type == "run_item_stream_event" and event.name == "tool_called":
                raw = event.item.raw_item
                yield {"type": "tool", "name": model.tool_names.get(raw.call_id, raw.name)}
        if result.run_loop_exception is not None:
            raise result.run_loop_exception
    except MaxTurnsExceeded:
        yield {"type": "delta", "text": LIMIT_TEXT}
    finally:
        if not result.is_complete:
            result.cancel()
        try:
            await events.aclose()
        finally:
            if result.run_loop_task is not None:
                await asyncio.gather(result.run_loop_task, return_exceptions=True)
