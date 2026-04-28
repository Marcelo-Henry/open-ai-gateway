import json

import pytest

from kiro.streaming_core import KiroEvent
import kiro.streaming_anthropic as streaming_anthropic


class DummyResponse:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class DummyModelCache:
    def get_max_input_tokens(self, model: str) -> int:
        return 200000


def parse_sse_events(chunks: list[str]) -> list[dict]:
    events = []
    for chunk in chunks:
        lines = chunk.strip().splitlines()
        data_line = next(line for line in lines if line.startswith("data: "))
        events.append(json.loads(data_line[6:]))
    return events


@pytest.mark.asyncio
async def test_text_stream_emits_canonical_anthropic_sequence(monkeypatch):
    async def fake_parse_kiro_stream(response, first_token_timeout):
        yield KiroEvent(type="content", content="Alo")
        yield KiroEvent(type="content", content="?")
        yield KiroEvent(type="context_usage", context_usage_percentage=10.0)

    monkeypatch.setattr(streaming_anthropic, "parse_kiro_stream", fake_parse_kiro_stream)

    response = DummyResponse()
    chunks = []
    async for chunk in streaming_anthropic.stream_kiro_to_anthropic(
        response=response,
        model="claude-sonnet-4-6",
        model_cache=DummyModelCache(),
        auth_manager=object(),
        request_messages=[],
    ):
        chunks.append(chunk)

    events = parse_sse_events(chunks)
    event_types = [event["type"] for event in events]

    assert event_types == [
        "message_start",
        "content_block_start",
        "content_block_delta",
        "content_block_delta",
        "content_block_stop",
        "message_delta",
        "message_stop",
    ]
    assert response.closed is True


@pytest.mark.asyncio
async def test_as_reasoning_content_emits_thinking_blocks_for_anthropic(monkeypatch):
    async def fake_parse_kiro_stream(response, first_token_timeout):
        yield KiroEvent(type="thinking", thinking_content="internal reasoning")
        yield KiroEvent(type="content", content="final answer")
        yield KiroEvent(type="context_usage", context_usage_percentage=10.0)

    monkeypatch.setattr(streaming_anthropic, "parse_kiro_stream", fake_parse_kiro_stream)
    monkeypatch.setattr(streaming_anthropic, "FAKE_REASONING_HANDLING", "as_reasoning_content")

    response = DummyResponse()
    chunks = []
    async for chunk in streaming_anthropic.stream_kiro_to_anthropic(
        response=response,
        model="claude-sonnet-4-6",
        model_cache=DummyModelCache(),
        auth_manager=object(),
        request_messages=[],
    ):
        chunks.append(chunk)

    events = parse_sse_events(chunks)
    event_types = [event["type"] for event in events]

    assert event_types == [
        "message_start",
        "content_block_start",   # thinking block
        "content_block_delta",   # thinking_delta
        "content_block_stop",    # close thinking
        "content_block_start",   # text block
        "content_block_delta",   # text_delta
        "content_block_stop",    # close text
        "message_delta",
        "message_stop",
    ]

    thinking_start = events[1]
    assert thinking_start["content_block"]["type"] == "thinking"

    thinking_delta = events[2]
    assert thinking_delta["delta"]["type"] == "thinking_delta"
    assert thinking_delta["delta"]["thinking"] == "internal reasoning"

    text_deltas = [e for e in events if e.get("delta", {}).get("type") == "text_delta"]
    assert [e["delta"]["text"] for e in text_deltas] == ["final answer"]
