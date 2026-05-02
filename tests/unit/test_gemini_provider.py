# -*- coding: utf-8 -*-

"""
Tests for Gemini provider (kiro/gemini_provider.py).

Covers:
- is_gemini_model() routing predicate
- _convert_anthropic_messages_to_gemini() message translation
- _convert_anthropic_tools_to_gemini() tool format conversion
- stream_gemini_response() SSE stream translation (mocked httpx)
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kiro.gemini_auth import GeminiAuthType
from kiro.gemini_provider import (
    _convert_anthropic_messages_to_gemini,
    _convert_anthropic_tools_to_gemini,
    _make_block_stop_event,
    _make_message_delta_event,
    _make_message_start_event,
    _make_message_stop_event,
    _make_text_block_start_event,
    _make_text_delta_event,
    _make_tool_input_delta_event,
    _make_tool_use_block_start_event,
    is_gemini_model,
)


# ==================================================================================================
# Helpers
# ==================================================================================================


def _parse_sse_events(chunks: list) -> list:
    """Parse Anthropic SSE event strings into dicts."""
    events = []
    for chunk in chunks:
        for line in chunk.strip().split("\n"):
            if line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return events


async def _run_gemini_stream(sse_lines: list, model: str = "gemini-2.5-pro") -> list:
    """
    Helper: mock Gemini endpoint and collect stream output.

    Args:
        sse_lines: List of raw SSE lines to simulate from Gemini API
        model: Model name to pass to stream_gemini_response

    Returns:
        List of SSE event strings yielded by stream_gemini_response
    """
    from kiro.gemini_provider import stream_gemini_response

    class MockAsyncLineIterator:
        def __init__(self, lines):
            self._lines = iter(lines)

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._lines)
            except StopIteration:
                raise StopAsyncIteration

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.aiter_lines = lambda: MockAsyncLineIterator(sse_lines)

    mock_stream_cm = MagicMock()
    mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_stream_cm)

    request_data = {
        "model": model,
        "messages": [{"role": "user", "content": "test"}],
    }

    with patch("kiro.gemini_provider.get_gemini_auth_headers", AsyncMock(return_value={"x-goog-api-key": "test-key"})):
        with patch("kiro.gemini_provider.get_auth_type", return_value=GeminiAuthType.API_KEY):
            with patch("kiro.gemini_provider._get_gemini_client", return_value=mock_client):
                chunks = []
                async for chunk in stream_gemini_response(request_data, model):
                    chunks.append(chunk)

    return chunks


# ==================================================================================================
# TestIsGeminiModel
# ==================================================================================================


class TestIsGeminiModel:
    """Tests for the is_gemini_model() routing predicate."""

    def test_gemini_prefix_returns_true(self):
        """'gemini-2.5-pro' should be routed to Gemini."""
        assert is_gemini_model("gemini-2.5-pro") is True

    def test_gemini_flash_returns_true(self):
        """'gemini-2.5-flash' should be routed to Gemini."""
        assert is_gemini_model("gemini-2.5-flash") is True

    def test_non_gemini_returns_false(self):
        """'claude-3.5-sonnet' should NOT be routed to Gemini."""
        assert is_gemini_model("claude-3.5-sonnet") is False

    def test_gpt_returns_false(self):
        """'gpt-5.4' should NOT be routed to Gemini."""
        assert is_gemini_model("gpt-5.4") is False

    def test_case_insensitive(self):
        """Model name check is case-insensitive."""
        assert is_gemini_model("GEMINI-2.5-PRO") is True
        assert is_gemini_model("Gemini-2.0-Flash") is True

    def test_empty_string_returns_false(self):
        """Empty model name returns False."""
        assert is_gemini_model("") is False

    def test_partial_prefix_returns_false(self):
        """'gem' alone does not match the 'gemini-' prefix."""
        assert is_gemini_model("gem-model") is False


# ==================================================================================================
# TestConvertAnthropicMessagesToGemini
# ==================================================================================================


class TestConvertAnthropicMessagesToGemini:
    """Tests for _convert_anthropic_messages_to_gemini()."""

    def test_simple_text_message(self):
        """User text message is converted to Gemini user content."""
        messages = [{"role": "user", "content": "Hello, Gemini!"}]
        result = _convert_anthropic_messages_to_gemini(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["parts"] == [{"text": "Hello, Gemini!"}]

    def test_assistant_role_becomes_model(self):
        """Anthropic 'assistant' role maps to Gemini 'model' role."""
        messages = [{"role": "assistant", "content": "Hi there!"}]
        result = _convert_anthropic_messages_to_gemini(messages)

        assert result[0]["role"] == "model"
        assert result[0]["parts"] == [{"text": "Hi there!"}]

    def test_string_content_becomes_text_part(self):
        """String content is wrapped in a single text part."""
        messages = [{"role": "user", "content": "Just a string"}]
        result = _convert_anthropic_messages_to_gemini(messages)

        assert result[0]["parts"] == [{"text": "Just a string"}]

    def test_text_block_in_list_content(self):
        """Text content block in a list is converted to a text part."""
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "Block text"}],
            }
        ]
        result = _convert_anthropic_messages_to_gemini(messages)

        assert result[0]["parts"] == [{"text": "Block text"}]

    def test_tool_use_block_becomes_function_call(self):
        """tool_use content block is converted to a functionCall part."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "get_weather",
                        "input": {"city": "London"},
                    }
                ],
            }
        ]
        result = _convert_anthropic_messages_to_gemini(messages)

        assert len(result) == 1
        assert result[0]["role"] == "model"
        parts = result[0]["parts"]
        assert len(parts) == 1
        assert "functionCall" in parts[0]
        assert parts[0]["functionCall"]["name"] == "get_weather"
        assert parts[0]["functionCall"]["args"] == {"city": "London"}

    def test_tool_result_block_becomes_function_response(self):
        """tool_result block is converted to a functionResponse part with correct name lookup."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_abc",
                        "name": "get_weather",
                        "input": {"city": "NYC"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc",
                        "content": "Sunny, 72°F",
                    }
                ],
            },
        ]
        result = _convert_anthropic_messages_to_gemini(messages)

        # Second content entry is the tool result
        tool_result_content = result[1]
        assert tool_result_content["role"] == "user"
        parts = tool_result_content["parts"]
        assert len(parts) == 1
        assert "functionResponse" in parts[0]
        assert parts[0]["functionResponse"]["name"] == "get_weather"
        assert parts[0]["functionResponse"]["response"] == {"result": "Sunny, 72°F"}

    def test_mixed_text_and_tool_use(self):
        """Message with both text and tool_use produces multiple parts."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {
                        "type": "tool_use",
                        "id": "toolu_xyz",
                        "name": "search",
                        "input": {"query": "test"},
                    },
                ],
            }
        ]
        result = _convert_anthropic_messages_to_gemini(messages)

        assert len(result) == 1
        parts = result[0]["parts"]
        assert len(parts) == 2
        assert parts[0] == {"text": "Let me check."}
        assert "functionCall" in parts[1]
        assert parts[1]["functionCall"]["name"] == "search"

    def test_empty_messages_returns_empty(self):
        """Empty messages list returns empty list."""
        assert _convert_anthropic_messages_to_gemini([]) == []

    def test_tool_result_with_list_content(self):
        """tool_result with list content extracts text from content blocks."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "call_1", "name": "my_tool", "input": {}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": [{"type": "text", "text": "result text"}],
                    }
                ],
            },
        ]
        result = _convert_anthropic_messages_to_gemini(messages)
        tool_result_parts = result[1]["parts"]
        assert tool_result_parts[0]["functionResponse"]["response"] == {"result": "result text"}

    def test_empty_text_block_is_skipped(self):
        """Empty text blocks are not added as parts."""
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": ""}],
            }
        ]
        result = _convert_anthropic_messages_to_gemini(messages)
        # Empty text → no parts → no content entry
        assert result == []


# ==================================================================================================
# TestConvertAnthropicToolsToGemini
# ==================================================================================================


class TestConvertAnthropicToolsToGemini:
    """Tests for _convert_anthropic_tools_to_gemini()."""

    def test_basic_tool_conversion(self):
        """input_schema is renamed to parameters; other fields are preserved."""
        tools = [
            {
                "name": "get_weather",
                "description": "Get current weather",
                "input_schema": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            }
        ]
        result = _convert_anthropic_tools_to_gemini(tools)

        assert len(result) == 1
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get current weather"
        assert result[0]["parameters"]["type"] == "object"
        assert "city" in result[0]["parameters"]["properties"]
        assert "input_schema" not in result[0]

    def test_empty_tools_returns_empty(self):
        """None and empty list both return empty list."""
        assert _convert_anthropic_tools_to_gemini(None) == []
        assert _convert_anthropic_tools_to_gemini([]) == []

    def test_tool_without_description(self):
        """Tool without description is included without a description key."""
        tools = [
            {
                "name": "my_tool",
                "input_schema": {"type": "object", "properties": {}},
            }
        ]
        result = _convert_anthropic_tools_to_gemini(tools)

        assert len(result) == 1
        assert result[0]["name"] == "my_tool"
        assert "description" not in result[0]

    def test_multiple_tools(self):
        """Multiple tools are all converted."""
        tools = [
            {"name": "tool_a", "description": "A", "input_schema": {}},
            {"name": "tool_b", "description": "B", "input_schema": {}},
        ]
        result = _convert_anthropic_tools_to_gemini(tools)
        assert len(result) == 2
        assert result[0]["name"] == "tool_a"
        assert result[1]["name"] == "tool_b"

    def test_skips_tool_with_empty_name(self):
        """Tools with empty name are skipped."""
        tools = [
            {"name": "", "description": "bad", "input_schema": {}},
            {"name": "good_tool", "description": "ok", "input_schema": {}},
        ]
        result = _convert_anthropic_tools_to_gemini(tools)
        assert len(result) == 1
        assert result[0]["name"] == "good_tool"

    def test_parameters_field_as_fallback(self):
        """'parameters' field is used when 'input_schema' is absent."""
        tools = [
            {
                "name": "my_tool",
                "description": "desc",
                "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
            }
        ]
        result = _convert_anthropic_tools_to_gemini(tools)
        assert result[0]["parameters"]["properties"]["x"]["type"] == "integer"


# ==================================================================================================
# TestStreamGeminiResponse
# ==================================================================================================


class TestStreamGeminiResponse:
    """Tests for stream_gemini_response() with mocked httpx."""

    @pytest.mark.asyncio
    async def test_text_response_emits_anthropic_events(self):
        """Text chunk from Gemini produces correct Anthropic SSE events."""
        sse_lines = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hello"}]}, "finishReason": ""}]}',
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"text": " world"}]}, "finishReason": "STOP"}]}',
        ]

        chunks = await _run_gemini_stream(sse_lines)
        events = _parse_sse_events(chunks)

        types = [e["type"] for e in events]
        assert "message_start" in types
        assert "content_block_start" in types
        assert "content_block_delta" in types
        assert "content_block_stop" in types
        assert "message_delta" in types
        assert "message_stop" in types

        # Verify text deltas
        text_deltas = [
            e for e in events
            if e["type"] == "content_block_delta"
            and e.get("delta", {}).get("type") == "text_delta"
        ]
        assert len(text_deltas) == 2
        assert text_deltas[0]["delta"]["text"] == "Hello"
        assert text_deltas[1]["delta"]["text"] == " world"

        # stop_reason should be end_turn (no tool calls)
        delta_events = [e for e in events if e["type"] == "message_delta"]
        assert delta_events[0]["delta"]["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_tool_call_response_emits_tool_use_events(self):
        """functionCall part from Gemini produces Anthropic tool_use SSE events."""
        sse_lines = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "get_weather", "args": {"city": "NYC"}}}]}, "finishReason": "STOP"}]}',
        ]

        chunks = await _run_gemini_stream(sse_lines)
        events = _parse_sse_events(chunks)

        # Find tool_use content_block_start
        block_starts = [e for e in events if e["type"] == "content_block_start"]
        tool_starts = [
            e for e in block_starts
            if e.get("content_block", {}).get("type") == "tool_use"
        ]
        assert len(tool_starts) == 1
        assert tool_starts[0]["content_block"]["name"] == "get_weather"
        assert tool_starts[0]["content_block"]["id"].startswith("toolu_")

        # Find input_json_delta
        input_deltas = [
            e for e in events
            if e["type"] == "content_block_delta"
            and e.get("delta", {}).get("type") == "input_json_delta"
        ]
        assert len(input_deltas) == 1
        args = json.loads(input_deltas[0]["delta"]["partial_json"])
        assert args == {"city": "NYC"}

        # stop_reason should be tool_use
        delta_events = [e for e in events if e["type"] == "message_delta"]
        assert delta_events[0]["delta"]["stop_reason"] == "tool_use"

    @pytest.mark.asyncio
    async def test_401_raises_http_exception(self):
        """401 response from Gemini raises HTTPException with status 401."""
        from fastapi import HTTPException

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.aread = AsyncMock(return_value=b"Unauthorized")

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        from kiro.gemini_provider import stream_gemini_response

        request_data = {"model": "gemini-2.5-pro", "messages": [{"role": "user", "content": "hi"}]}

        with patch("kiro.gemini_provider.get_gemini_auth_headers", AsyncMock(return_value={"x-goog-api-key": "key"})):
            with patch("kiro.gemini_provider.get_auth_type", return_value=GeminiAuthType.API_KEY):
                with patch("kiro.gemini_provider._get_gemini_client", return_value=mock_client):
                    with pytest.raises(HTTPException) as exc_info:
                        async for _ in stream_gemini_response(request_data, "gemini-2.5-pro"):
                            pass

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_429_raises_http_exception(self):
        """429 response from Gemini raises HTTPException with status 429."""
        from fastapi import HTTPException

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.aread = AsyncMock(return_value=b"Rate limited")

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        from kiro.gemini_provider import stream_gemini_response

        request_data = {"model": "gemini-2.5-pro", "messages": [{"role": "user", "content": "hi"}]}

        with patch("kiro.gemini_provider.get_gemini_auth_headers", AsyncMock(return_value={"x-goog-api-key": "key"})):
            with patch("kiro.gemini_provider.get_auth_type", return_value=GeminiAuthType.API_KEY):
                with patch("kiro.gemini_provider._get_gemini_client", return_value=mock_client):
                    with pytest.raises(HTTPException) as exc_info:
                        async for _ in stream_gemini_response(request_data, "gemini-2.5-pro"):
                            pass

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_timeout_raises_504(self):
        """httpx.TimeoutException raises HTTPException with status 504."""
        import httpx
        from fastapi import HTTPException

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        from kiro.gemini_provider import stream_gemini_response

        request_data = {"model": "gemini-2.5-pro", "messages": [{"role": "user", "content": "hi"}]}

        with patch("kiro.gemini_provider.get_gemini_auth_headers", AsyncMock(return_value={"x-goog-api-key": "key"})):
            with patch("kiro.gemini_provider.get_auth_type", return_value=GeminiAuthType.API_KEY):
                with patch("kiro.gemini_provider._get_gemini_client", return_value=mock_client):
                    with pytest.raises(HTTPException) as exc_info:
                        async for _ in stream_gemini_response(request_data, "gemini-2.5-pro"):
                            pass

        assert exc_info.value.status_code == 504

    @pytest.mark.asyncio
    async def test_network_error_raises_503(self):
        """httpx.RequestError raises HTTPException with status 503."""
        import httpx
        from fastapi import HTTPException

        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        from kiro.gemini_provider import stream_gemini_response

        request_data = {"model": "gemini-2.5-pro", "messages": [{"role": "user", "content": "hi"}]}

        with patch("kiro.gemini_provider.get_gemini_auth_headers", AsyncMock(return_value={"x-goog-api-key": "key"})):
            with patch("kiro.gemini_provider.get_auth_type", return_value=GeminiAuthType.API_KEY):
                with patch("kiro.gemini_provider._get_gemini_client", return_value=mock_client):
                    with pytest.raises(HTTPException) as exc_info:
                        async for _ in stream_gemini_response(request_data, "gemini-2.5-pro"):
                            pass

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_empty_response_emits_empty_text_block(self):
        """Empty Gemini response still emits an empty text block."""
        sse_lines = [
            'data: {"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": "STOP"}]}',
        ]

        chunks = await _run_gemini_stream(sse_lines)
        events = _parse_sse_events(chunks)

        block_starts = [e for e in events if e["type"] == "content_block_start"]
        assert len(block_starts) == 1
        assert block_starts[0]["content_block"]["type"] == "text"

    @pytest.mark.asyncio
    async def test_no_candidates_in_chunk_is_skipped(self):
        """Chunks with no candidates are silently skipped."""
        sse_lines = [
            'data: {"usageMetadata": {"promptTokenCount": 10}}',
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hi"}]}, "finishReason": "STOP"}]}',
        ]

        chunks = await _run_gemini_stream(sse_lines)
        events = _parse_sse_events(chunks)

        text_deltas = [
            e for e in events
            if e["type"] == "content_block_delta"
            and e.get("delta", {}).get("type") == "text_delta"
        ]
        assert len(text_deltas) == 1
        assert text_deltas[0]["delta"]["text"] == "Hi"

    @pytest.mark.asyncio
    async def test_message_start_contains_model_name(self):
        """message_start event contains the correct model name."""
        sse_lines = [
            'data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}, "finishReason": "STOP"}]}',
        ]

        chunks = await _run_gemini_stream(sse_lines, model="gemini-2.5-flash")
        events = _parse_sse_events(chunks)

        start_events = [e for e in events if e["type"] == "message_start"]
        assert len(start_events) == 1
        assert start_events[0]["message"]["model"] == "gemini-2.5-flash"


# ==================================================================================================
# TestSSEEventHelpers
# ==================================================================================================


class TestGeminiSSEEventHelpers:
    """Tests for Anthropic SSE event builder functions in gemini_provider."""

    def test_message_start(self):
        event_str = _make_message_start_event("gemini-2.5-pro", "msg_abc")
        data = json.loads(event_str.split("data: ")[1])
        assert data["type"] == "message_start"
        assert data["message"]["model"] == "gemini-2.5-pro"
        assert data["message"]["id"] == "msg_abc"

    def test_text_block_start(self):
        event_str = _make_text_block_start_event(0)
        assert "event: content_block_start" in event_str
        data = json.loads(event_str.split("data: ")[1])
        assert data["index"] == 0
        assert data["content_block"]["type"] == "text"

    def test_text_delta(self):
        event_str = _make_text_delta_event(0, "hello")
        data = json.loads(event_str.split("data: ")[1])
        assert data["delta"]["type"] == "text_delta"
        assert data["delta"]["text"] == "hello"

    def test_tool_use_block_start(self):
        event_str = _make_tool_use_block_start_event(1, "toolu_abc", "get_weather")
        data = json.loads(event_str.split("data: ")[1])
        assert data["content_block"]["type"] == "tool_use"
        assert data["content_block"]["id"] == "toolu_abc"
        assert data["content_block"]["name"] == "get_weather"

    def test_tool_input_delta(self):
        event_str = _make_tool_input_delta_event(1, '{"city":')
        data = json.loads(event_str.split("data: ")[1])
        assert data["delta"]["type"] == "input_json_delta"
        assert data["delta"]["partial_json"] == '{"city":'

    def test_block_stop(self):
        event_str = _make_block_stop_event(2)
        data = json.loads(event_str.split("data: ")[1])
        assert data["type"] == "content_block_stop"
        assert data["index"] == 2

    def test_message_delta_default_stop_reason(self):
        event_str = _make_message_delta_event()
        data = json.loads(event_str.split("data: ")[1])
        assert data["delta"]["stop_reason"] == "end_turn"

    def test_message_delta_tool_use_stop_reason(self):
        event_str = _make_message_delta_event("tool_use")
        data = json.loads(event_str.split("data: ")[1])
        assert data["delta"]["stop_reason"] == "tool_use"

    def test_message_stop(self):
        event_str = _make_message_stop_event()
        data = json.loads(event_str.split("data: ")[1])
        assert data["type"] == "message_stop"
