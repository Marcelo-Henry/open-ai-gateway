# -*- coding: utf-8 -*-

"""
Tests for Codex provider tool call support.

Covers:
- Tool format conversion (Anthropic → Codex Responses API)
- Message conversion with tool_use and tool_result blocks
- Payload building with tools
- SSE event helpers for tool_use blocks
- Stream translation (Codex → Anthropic SSE) with tool calls
- OpenAI route: tool passthrough and streaming translation
- Anthropic route: non-streaming tool collection
"""

import json
import pytest

from kiro.codex_provider import (
    _convert_tools_to_codex_format,
    _convert_messages_with_tool_content,
    _build_codex_payload,
    _make_message_start_event,
    _make_text_block_start_event,
    _make_text_delta_event,
    _make_tool_use_block_start_event,
    _make_tool_input_delta_event,
    _make_block_stop_event,
    _make_message_delta_event,
    _make_message_stop_event,
)


# ==================================================================================================
# _convert_tools_to_codex_format
# ==================================================================================================


class TestConvertToolsToCodexFormat:
    """Tests for Anthropic → Codex tool format conversion."""

    def test_single_tool(self):
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
        result = _convert_tools_to_codex_format(tools)

        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["name"] == "get_weather"
        assert result[0]["description"] == "Get current weather"
        assert result[0]["parameters"]["type"] == "object"
        assert "city" in result[0]["parameters"]["properties"]

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A", "input_schema": {}},
            {"name": "tool_b", "description": "B", "input_schema": {}},
            {"name": "tool_c", "description": "C", "input_schema": {}},
        ]
        result = _convert_tools_to_codex_format(tools)
        assert len(result) == 3
        assert [t["name"] for t in result] == ["tool_a", "tool_b", "tool_c"]

    def test_empty_list(self):
        assert _convert_tools_to_codex_format([]) == []

    def test_missing_description_gets_placeholder(self):
        tools = [{"name": "my_tool", "input_schema": {}}]
        result = _convert_tools_to_codex_format(tools)
        assert result[0]["description"] == "Tool: my_tool"

    def test_missing_input_schema_defaults_to_empty(self):
        tools = [{"name": "my_tool", "description": "desc"}]
        result = _convert_tools_to_codex_format(tools)
        assert result[0]["parameters"] == {}

    def test_skips_tool_with_empty_name(self):
        tools = [
            {"name": "", "description": "bad"},
            {"name": "good_tool", "description": "ok", "input_schema": {}},
        ]
        result = _convert_tools_to_codex_format(tools)
        assert len(result) == 1
        assert result[0]["name"] == "good_tool"

    def test_parameters_field_as_fallback(self):
        """Some clients send 'parameters' instead of 'input_schema'."""
        tools = [
            {
                "name": "my_tool",
                "description": "desc",
                "parameters": {"type": "object", "properties": {"x": {"type": "integer"}}},
            }
        ]
        result = _convert_tools_to_codex_format(tools)
        assert result[0]["parameters"]["properties"]["x"]["type"] == "integer"

    def test_input_schema_takes_priority_over_parameters(self):
        tools = [
            {
                "name": "my_tool",
                "description": "desc",
                "input_schema": {"type": "object", "properties": {"a": {"type": "string"}}},
                "parameters": {"type": "object", "properties": {"b": {"type": "integer"}}},
            }
        ]
        result = _convert_tools_to_codex_format(tools)
        assert "a" in result[0]["parameters"]["properties"]
        assert "b" not in result[0]["parameters"]["properties"]


# ==================================================================================================
# _convert_messages_with_tool_content
# ==================================================================================================


class TestConvertMessagesWithToolContent:
    """Tests for message conversion with tool_use and tool_result blocks."""

    def test_simple_text_messages(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = _convert_messages_with_tool_content(messages)
        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi there"}

    def test_tool_use_in_assistant_message(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {
                        "type": "tool_use",
                        "id": "toolu_abc123",
                        "name": "get_weather",
                        "input": {"city": "London"},
                    },
                ],
            }
        ]
        result = _convert_messages_with_tool_content(messages)

        # Should produce: text message + function_call item
        assert len(result) == 2
        assert result[0] == {"role": "assistant", "content": "Let me check."}
        assert result[1]["type"] == "function_call"
        assert result[1]["name"] == "get_weather"
        assert result[1]["call_id"] == "toolu_abc123"
        assert json.loads(result[1]["arguments"]) == {"city": "London"}

    def test_tool_result_in_user_message(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_abc123",
                        "content": "Sunny, 22°C",
                    }
                ],
            }
        ]
        result = _convert_messages_with_tool_content(messages)

        assert len(result) == 1
        assert result[0]["type"] == "function_call_output"
        assert result[0]["call_id"] == "toolu_abc123"
        assert result[0]["output"] == "Sunny, 22°C"

    def test_tool_result_with_empty_content(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "call_1", "content": ""},
                ],
            }
        ]
        result = _convert_messages_with_tool_content(messages)
        assert result[0]["output"] == "(empty result)"

    def test_mixed_text_and_tool_use(self):
        """Assistant message with text + multiple tool calls."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll check both."},
                    {"type": "tool_use", "id": "call_1", "name": "tool_a", "input": {"x": 1}},
                    {"type": "tool_use", "id": "call_2", "name": "tool_b", "input": {"y": 2}},
                ],
            }
        ]
        result = _convert_messages_with_tool_content(messages)
        assert len(result) == 3
        assert result[0]["role"] == "assistant"
        assert result[1]["type"] == "function_call"
        assert result[1]["name"] == "tool_a"
        assert result[2]["type"] == "function_call"
        assert result[2]["name"] == "tool_b"

    def test_string_content_message(self):
        messages = [{"role": "user", "content": "Just text"}]
        result = _convert_messages_with_tool_content(messages)
        assert result == [{"role": "user", "content": "Just text"}]

    def test_empty_messages(self):
        assert _convert_messages_with_tool_content([]) == []

    def test_tool_result_with_list_content(self):
        """Tool result content can be a list of content blocks."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": [{"type": "text", "text": "result text"}],
                    }
                ],
            }
        ]
        result = _convert_messages_with_tool_content(messages)
        assert result[0]["output"] == "result text"


# ==================================================================================================
# _build_codex_payload
# ==================================================================================================


class TestBuildCodexPayload:
    """Tests for payload building with tools."""

    def test_payload_without_tools(self):
        request_data = {
            "model": "gpt-5.4",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        payload = _build_codex_payload(request_data, "gpt-5.4", "System prompt")

        assert "tools" not in payload
        assert payload["model"] == "gpt-5.4"
        assert payload["stream"] is True

    def test_payload_with_tools(self):
        request_data = {
            "model": "gpt-5.4",
            "messages": [{"role": "user", "content": "What's the weather?"}],
            "tools": [
                {
                    "name": "get_weather",
                    "description": "Get weather",
                    "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
                }
            ],
        }
        payload = _build_codex_payload(request_data, "gpt-5.4", "System prompt")

        assert "tools" in payload
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["name"] == "get_weather"

    def test_payload_with_empty_tools_list(self):
        request_data = {
            "model": "gpt-5.4",
            "messages": [{"role": "user", "content": "Hello"}],
            "tools": [],
        }
        payload = _build_codex_payload(request_data, "gpt-5.4", "System prompt")
        assert "tools" not in payload

    def test_payload_with_tool_use_in_history(self):
        request_data = {
            "model": "gpt-5.4",
            "messages": [
                {"role": "user", "content": "What's the weather in London?"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "call_1", "name": "get_weather", "input": {"city": "London"}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "call_1", "content": "Sunny, 22°C"},
                    ],
                },
            ],
            "tools": [{"name": "get_weather", "description": "Get weather", "input_schema": {}}],
        }
        payload = _build_codex_payload(request_data, "gpt-5.4", "System prompt")

        # Should have: developer + user text + function_call + function_call_output
        input_msgs = payload["input"]
        assert input_msgs[0]["role"] == "developer"
        assert input_msgs[1]["role"] == "user"
        assert input_msgs[2]["type"] == "function_call"
        assert input_msgs[3]["type"] == "function_call_output"

    def test_system_prompt_merging(self):
        request_data = {
            "model": "gpt-5.4",
            "messages": [{"role": "user", "content": "Hi"}],
            "system": "Custom system prompt",
        }
        payload = _build_codex_payload(request_data, "gpt-5.4", "Default prompt")

        developer_msg = payload["input"][0]
        assert "Default prompt" in developer_msg["content"]
        assert "Custom system prompt" in developer_msg["content"]


# ==================================================================================================
# SSE Event Helpers
# ==================================================================================================


class TestSSEEventHelpers:
    """Tests for Anthropic SSE event builder functions."""

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
        assert data["index"] == 0

    def test_tool_use_block_start(self):
        event_str = _make_tool_use_block_start_event(1, "toolu_abc", "get_weather")
        assert "event: content_block_start" in event_str
        data = json.loads(event_str.split("data: ")[1])
        assert data["index"] == 1
        assert data["content_block"]["type"] == "tool_use"
        assert data["content_block"]["id"] == "toolu_abc"
        assert data["content_block"]["name"] == "get_weather"
        assert data["content_block"]["input"] == {}

    def test_tool_input_delta(self):
        event_str = _make_tool_input_delta_event(1, '{"city":')
        data = json.loads(event_str.split("data: ")[1])
        assert data["index"] == 1
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

    def test_message_start(self):
        event_str = _make_message_start_event("gpt-5.4", "msg_abc")
        data = json.loads(event_str.split("data: ")[1])
        assert data["type"] == "message_start"
        assert data["message"]["model"] == "gpt-5.4"
        assert data["message"]["id"] == "msg_abc"

    def test_message_stop(self):
        event_str = _make_message_stop_event()
        data = json.loads(event_str.split("data: ")[1])
        assert data["type"] == "message_stop"

    def test_text_block_start_at_nonzero_index(self):
        event_str = _make_text_block_start_event(3)
        data = json.loads(event_str.split("data: ")[1])
        assert data["index"] == 3

    def test_tool_input_delta_with_unicode(self):
        event_str = _make_tool_input_delta_event(0, '{"query": "café"}')
        data = json.loads(event_str.split("data: ")[1])
        assert "café" in data["delta"]["partial_json"]


# ==================================================================================================
# Stream Translation (integration-style, mocking httpx)
# ==================================================================================================


class TestStreamCodexResponseToolCalls:
    """Tests for stream_codex_response with tool call events."""

    @staticmethod
    def _parse_sse_events(chunks: list[str]) -> list[dict]:
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

    @pytest.mark.asyncio
    async def test_text_only_stream(self, monkeypatch):
        """Text-only response produces correct Anthropic events."""
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": "Hello "}',
            'data: {"type": "response.output_text.delta", "delta": "world"}',
            'data: {"type": "response.output_text.done", "text": "Hello world"}',
            'data: {"type": "response.completed"}',
        ]

        chunks = await self._run_stream(monkeypatch, sse_lines)
        events = self._parse_sse_events(chunks)

        # Should have: message_start, content_block_start(text), 2x delta, block_stop, message_delta, message_stop
        types = [e["type"] for e in events]
        assert "message_start" in types
        assert types.count("content_block_delta") == 2
        assert "content_block_stop" in types

        # stop_reason should be end_turn
        delta_events = [e for e in events if e["type"] == "message_delta"]
        assert delta_events[0]["delta"]["stop_reason"] == "end_turn"

    @pytest.mark.asyncio
    async def test_tool_call_stream(self, monkeypatch):
        """Tool call response produces correct Anthropic tool_use events."""
        sse_lines = [
            'data: {"type": "response.output_item.added", "item": {"type": "function_call", "name": "get_weather", "call_id": "call_abc123"}}',
            'data: {"type": "response.function_call_arguments.delta", "delta": "{\\"city\\":"}',
            'data: {"type": "response.function_call_arguments.delta", "delta": " \\"London\\"}"}',
            'data: {"type": "response.function_call_arguments.done", "arguments": "{\\"city\\": \\"London\\"}"}',
            'data: {"type": "response.completed"}',
        ]

        chunks = await self._run_stream(monkeypatch, sse_lines)
        events = self._parse_sse_events(chunks)

        # Find tool_use content_block_start
        block_starts = [e for e in events if e["type"] == "content_block_start"]
        tool_starts = [e for e in block_starts if e.get("content_block", {}).get("type") == "tool_use"]
        assert len(tool_starts) == 1
        assert tool_starts[0]["content_block"]["name"] == "get_weather"
        assert tool_starts[0]["content_block"]["id"] == "call_abc123"

        # Find input_json_delta events
        input_deltas = [
            e for e in events
            if e["type"] == "content_block_delta" and e.get("delta", {}).get("type") == "input_json_delta"
        ]
        assert len(input_deltas) == 2

        # stop_reason should be tool_use
        delta_events = [e for e in events if e["type"] == "message_delta"]
        assert delta_events[0]["delta"]["stop_reason"] == "tool_use"

    @pytest.mark.asyncio
    async def test_mixed_text_and_tool_stream(self, monkeypatch):
        """Response with text followed by tool call."""
        sse_lines = [
            'data: {"type": "response.output_text.delta", "delta": "Let me check."}',
            'data: {"type": "response.output_text.done", "text": "Let me check."}',
            'data: {"type": "response.output_item.added", "item": {"type": "function_call", "name": "search", "call_id": "call_xyz"}}',
            'data: {"type": "response.function_call_arguments.delta", "delta": "{\\"q\\": \\"test\\"}"}',
            'data: {"type": "response.function_call_arguments.done", "arguments": "{\\"q\\": \\"test\\"}"}',
            'data: {"type": "response.completed"}',
        ]

        chunks = await self._run_stream(monkeypatch, sse_lines)
        events = self._parse_sse_events(chunks)

        # Should have both text and tool blocks
        block_starts = [e for e in events if e["type"] == "content_block_start"]
        text_starts = [e for e in block_starts if e.get("content_block", {}).get("type") == "text"]
        tool_starts = [e for e in block_starts if e.get("content_block", {}).get("type") == "tool_use"]
        assert len(text_starts) == 1
        assert len(tool_starts) == 1

        # Text block should be at index 0, tool at index 1
        assert text_starts[0]["index"] == 0
        assert tool_starts[0]["index"] == 1

        # stop_reason should be tool_use (tools take priority)
        delta_events = [e for e in events if e["type"] == "message_delta"]
        assert delta_events[0]["delta"]["stop_reason"] == "tool_use"

    @pytest.mark.asyncio
    async def test_empty_response_emits_empty_text_block(self, monkeypatch):
        """Empty response still emits a text block."""
        sse_lines = [
            'data: {"type": "response.completed"}',
        ]

        chunks = await self._run_stream(monkeypatch, sse_lines)
        events = self._parse_sse_events(chunks)

        block_starts = [e for e in events if e["type"] == "content_block_start"]
        assert len(block_starts) == 1
        assert block_starts[0]["content_block"]["type"] == "text"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, monkeypatch):
        """Multiple tool calls in a single response."""
        sse_lines = [
            'data: {"type": "response.output_item.added", "item": {"type": "function_call", "name": "tool_a", "call_id": "call_1"}}',
            'data: {"type": "response.function_call_arguments.delta", "delta": "{}"}',
            'data: {"type": "response.function_call_arguments.done", "arguments": "{}"}',
            'data: {"type": "response.output_item.added", "item": {"type": "function_call", "name": "tool_b", "call_id": "call_2"}}',
            'data: {"type": "response.function_call_arguments.delta", "delta": "{\\"x\\": 1}"}',
            'data: {"type": "response.function_call_arguments.done", "arguments": "{\\"x\\": 1}"}',
            'data: {"type": "response.completed"}',
        ]

        chunks = await self._run_stream(monkeypatch, sse_lines)
        events = self._parse_sse_events(chunks)

        tool_starts = [
            e for e in events
            if e["type"] == "content_block_start" and e.get("content_block", {}).get("type") == "tool_use"
        ]
        assert len(tool_starts) == 2
        assert tool_starts[0]["content_block"]["name"] == "tool_a"
        assert tool_starts[1]["content_block"]["name"] == "tool_b"
        assert tool_starts[0]["index"] == 0
        assert tool_starts[1]["index"] == 1

    async def _run_stream(self, monkeypatch, sse_lines: list[str]) -> list[str]:
        """Helper: mock Codex endpoint and collect stream output."""
        import httpx
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock get_codex_token
        monkeypatch.setattr("kiro.codex_provider.get_codex_token", AsyncMock(return_value="fake_token"))

        # Mock get_codex_system_prompt
        monkeypatch.setattr("kiro.codex_provider.get_codex_system_prompt", AsyncMock(return_value="System"))

        # Build a mock response that yields SSE lines
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

        # Mock httpx.AsyncClient context manager
        mock_stream_cm = MagicMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_cm)

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("kiro.codex_provider.httpx.AsyncClient", return_value=mock_client_cm):
            from kiro.codex_provider import stream_codex_response

            request_data = {
                "model": "gpt-5.4",
                "messages": [{"role": "user", "content": "test"}],
            }

            chunks = []
            async for chunk in stream_codex_response(request_data, "gpt-5.4"):
                chunks.append(chunk)

        return chunks
