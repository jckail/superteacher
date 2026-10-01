"""Fake Anthropic client pieces for offline tests."""

from types import SimpleNamespace as NS

import anthropic
import httpx


def text_block(t):
    return NS(type="text", text=t)


def tool_block(id, name, input):
    return NS(type="tool_use", id=id, name=name, input=input)


class FakeStream:
    def __init__(self, texts, stop_reason, content, raises=None):
        self.texts, self.stop_reason, self.content, self.raises = texts, stop_reason, content, raises
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False

    @property
    def text_stream(self):
        async def gen():
            for t in self.texts:
                yield t
            if self.raises:
                raise self.raises

        return gen()

    async def get_final_message(self):
        return NS(stop_reason=self.stop_reason, content=self.content)


class FakeAI:
    """messages.stream pops scripted turns; messages.create pops scripted responses/exceptions."""

    def __init__(self, turns=(), creates=()):
        self.turns, self.creates = list(turns), list(creates)
        self.stream_calls, self.create_calls, self.streams = [], [], []
        self.messages = self

    def stream(self, **kw):
        self.stream_calls.append({**kw, "messages": [dict(m) for m in kw["messages"]]})
        s = self.turns.pop(0)
        self.streams.append(s)
        return s

    async def create(self, **kw):
        self.create_calls.append(kw)
        r = self.creates.pop(0)
        if isinstance(r, Exception):
            raise r
        return NS(content=[text_block(r)] if isinstance(r, str) else r)


def end_turn(*texts):
    return FakeStream(list(texts), "end_turn", [text_block("".join(texts))])


def tool_turn(id, name, input, *texts):
    return FakeStream(list(texts), "tool_use", [text_block("".join(texts)), tool_block(id, name, input)])


_req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def api_error(cls, status):
    return cls("secret internal detail", response=httpx.Response(status, request=_req), body=None)


def conn_error():
    return anthropic.APIConnectionError(request=_req)
