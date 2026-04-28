# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Codex CLI OAuth provider for Kiro Gateway.

Translates Anthropic Messages API requests to the OpenAI Responses API
format used by the private Codex endpoint, streams the response back
as Anthropic-compatible SSE events.

Endpoint: POST https://chatgpt.com/backend-api/codex/responses
Protocol: OpenAI Responses API (NOT Chat Completions)
Auth:      Bearer <access_token> from ~/.codex/auth.json
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import HTTPException
from loguru import logger

from kiro.codex_auth import get_codex_token
from kiro.config import CODEX_REASONING_EFFORT

# Private Codex endpoint
_CODEX_URL = "https://chatgpt.com/backend-api/codex/responses"

# GitHub URL for the official Codex system prompt
_CODEX_SYSTEM_PROMPT_URL = (
    "https://raw.githubusercontent.com/openai/codex/main/"
    "codex-rs/core/src/default_system_prompt.md"
)

# Fallback system prompt used when GitHub fetch fails
_FALLBACK_SYSTEM_PROMPT = (
    "You are Codex, a highly capable AI software engineering assistant made by OpenAI. "
    "You help users with coding tasks including writing, reviewing, and debugging code. "
    "You have access to tools that allow you to read and modify files. "
    "Be concise, accurate, and helpful."
)

# In-memory cache for the system prompt (fetched once per process lifetime)
_cached_system_prompt: Optional[str] = None

# Models available via Codex OAuth
CODEX_MODELS: List[Dict[str, str]] = [
    {"id": "gpt-5.5",              "display_name": "GPT-5.5 (Codex)"},
    {"id": "gpt-5.4",              "display_name": "GPT-5.4 (Codex)"},
    {"id": "gpt-5.4-mini",         "display_name": "GPT-5.4 Mini (Codex)"},
    {"id": "gpt-5.3-codex-spark",  "display_name": "GPT-5.3 Codex Spark (Codex)"},
]


def is_codex_model(model_name: str) -> bool:
    """
    Return True if the model should be routed to the Codex provider.

    Args:
        model_name: Model name from the client request

    Returns:
        True for gpt-* and codex-* prefixes, and codex-mini-latest
    """
    lower = model_name.lower()
    return (
        lower.startswith("gpt-")
        or lower.startswith("codex-")
        or lower == "codex-mini-latest"
    )


async def get_codex_system_prompt() -> str:
    """
    Return the Codex system prompt, fetching from GitHub on first call.

    Caches the result in memory for the process lifetime.
    Falls back to a hardcoded prompt if the fetch fails.

    Returns:
        System prompt string
    """
    global _cached_system_prompt

    if _cached_system_prompt is not None:
        return _cached_system_prompt

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(_CODEX_SYSTEM_PROMPT_URL)
            response.raise_for_status()
            _cached_system_prompt = response.text.strip()
            logger.debug("Codex system prompt fetched from GitHub")
    except Exception as e:
        logger.debug(f"Could not fetch Codex system prompt from GitHub ({e}), using fallback")
        _cached_system_prompt = _FALLBACK_SYSTEM_PROMPT

    return _cached_system_prompt


def _extract_text_from_content(content: Any) -> str:
    """
    Extract plain text from Anthropic content (string or list of blocks).

    Args:
        content: String or list of Anthropic content blocks

    Returns:
        Concatenated text string
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif hasattr(block, "type") and block.type == "text":
                parts.append(getattr(block, "text", ""))
        return "".join(parts)

    return str(content) if content is not None else ""


def _convert_tools_to_codex_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert Anthropic-format tools to OpenAI Responses API format.

    Anthropic: {"name": "x", "description": "y", "input_schema": {...}}
    Responses API: {"type": "function", "name": "x", "description": "y", "parameters": {...}}

    Args:
        tools: List of tools in Anthropic format

    Returns:
        List of tools in Responses API format
    """
    codex_tools: List[Dict[str, Any]] = []

    for tool in tools:
        if isinstance(tool, dict):
            name = tool.get("name", "")
            description = tool.get("description", "")
            parameters = tool.get("input_schema") or tool.get("parameters") or {}
        else:
            name = getattr(tool, "name", "")
            description = getattr(tool, "description", "")
            parameters = getattr(tool, "input_schema", None) or getattr(tool, "parameters", None) or {}

        if not name:
            logger.debug("Skipping tool with empty name")
            continue

        codex_tools.append({
            "type": "function",
            "name": name,
            "description": description or f"Tool: {name}",
            "parameters": parameters,
        })

    if codex_tools:
        logger.debug(f"Converted {len(codex_tools)} tool(s) to Codex format")

    return codex_tools


def _convert_messages_with_tool_content(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convert Anthropic messages to Codex input format, handling tool_use and tool_result blocks.

    Anthropic assistant messages may contain tool_use content blocks.
    Anthropic user messages may contain tool_result content blocks.
    These need to be translated to the Responses API conversation format.

    Args:
        messages: List of Anthropic messages (dicts)

    Returns:
        List of Codex input messages
    """
    codex_messages: List[Dict[str, Any]] = []

    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")

        codex_role = "assistant" if role == "assistant" else "user"

        if not isinstance(content, list):
            text = _extract_text_from_content(content)
            if text:
                codex_messages.append({"role": codex_role, "content": text})
            continue

        # Content is a list of blocks — process each type
        text_parts: List[str] = []
        tool_uses: List[Dict[str, Any]] = []
        tool_results: List[Dict[str, Any]] = []

        for block in content:
            if not isinstance(block, dict):
                if hasattr(block, "type"):
                    block = {"type": block.type, **{k: v for k, v in block.__dict__.items() if k != "type"}}
                else:
                    continue

            block_type = block.get("type", "")

            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_uses.append(block)
            elif block_type == "tool_result":
                tool_results.append(block)

        # Emit text content
        text = "".join(text_parts)
        if text:
            codex_messages.append({"role": codex_role, "content": text})

        # Emit tool calls as function_call output items
        for tu in tool_uses:
            tool_input = tu.get("input", {})
            if isinstance(tool_input, dict):
                args_str = json.dumps(tool_input)
            else:
                args_str = str(tool_input)

            codex_messages.append({
                "type": "function_call",
                "name": tu.get("name", ""),
                "call_id": tu.get("id", f"call_{uuid.uuid4().hex[:24]}"),
                "arguments": args_str,
            })

        # Emit tool results as function_call_output items
        for tr in tool_results:
            result_content = tr.get("content", "")
            if isinstance(result_content, list):
                result_content = _extract_text_from_content(result_content)
            elif not isinstance(result_content, str):
                result_content = str(result_content) if result_content else ""

            codex_messages.append({
                "type": "function_call_output",
                "call_id": tr.get("tool_use_id", ""),
                "output": result_content or "(empty result)",
            })

    return codex_messages


def _build_codex_payload(
    request_data: Dict[str, Any],
    model: str,
    system_prompt: str,
) -> Dict[str, Any]:
    """
    Translate an Anthropic Messages request dict to Codex Responses API format.

    Args:
        request_data: Anthropic request as a plain dict (model_dump() output)
        model: Model name to send to Codex
        system_prompt: System prompt string for the 'instructions' field

    Returns:
        Codex-format request payload dict
    """
    # Inject system prompt as the first 'developer' message
    effective_system = system_prompt

    anthropic_system = request_data.get("system")
    if anthropic_system:
        if isinstance(anthropic_system, list):
            system_text = _extract_text_from_content(anthropic_system)
        else:
            system_text = str(anthropic_system)

        if system_text.strip():
            effective_system = f"{system_prompt}\n\n---\n\n{system_text}"

    input_messages: List[Dict[str, Any]] = [
        {"role": "developer", "content": effective_system},
    ]

    # Translate conversation history (handles text, tool_use, and tool_result blocks)
    input_messages.extend(
        _convert_messages_with_tool_content(request_data.get("messages", []))
    )

    payload: Dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "instructions": effective_system,
        "store": False,
        "stream": True,
        "text": {
            "verbosity": "medium",
        },
    }

    # Only include reasoning config if effort is not "none"
    if CODEX_REASONING_EFFORT != "none":
        # xhigh uses summary=xhigh for maximum reasoning depth
        summary = "xhigh" if CODEX_REASONING_EFFORT == "xhigh" else "auto"
        payload["reasoning"] = {
            "effort": CODEX_REASONING_EFFORT,
            "summary": summary,
        }
        payload["include"] = ["reasoning.encrypted_content"]

    # Add tools if present
    anthropic_tools = request_data.get("tools")
    if anthropic_tools:
        codex_tools = _convert_tools_to_codex_format(anthropic_tools)
        if codex_tools:
            payload["tools"] = codex_tools

    return payload


def _make_message_start_event(model: str, message_id: str) -> str:
    """Build the Anthropic message_start SSE event string."""
    data = {
        "type": "message_start",
        "message": {
            "id": message_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    }
    return f"event: message_start\ndata: {json.dumps(data)}\n\n"


def _make_text_block_start_event(index: int) -> str:
    """Build Anthropic content_block_start for a text block."""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {"type": "text", "text": ""},
    }
    return f"event: content_block_start\ndata: {json.dumps(data)}\n\n"


def _make_text_delta_event(index: int, text: str) -> str:
    """Build Anthropic content_block_delta for text."""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "text_delta", "text": text},
    }
    return f"event: content_block_delta\ndata: {json.dumps(data)}\n\n"


def _make_tool_use_block_start_event(index: int, tool_id: str, tool_name: str) -> str:
    """Build Anthropic content_block_start for a tool_use block."""
    data = {
        "type": "content_block_start",
        "index": index,
        "content_block": {
            "type": "tool_use",
            "id": tool_id,
            "name": tool_name,
            "input": {},
        },
    }
    return f"event: content_block_start\ndata: {json.dumps(data)}\n\n"


def _make_tool_input_delta_event(index: int, partial_json: str) -> str:
    """Build Anthropic content_block_delta for tool input."""
    data = {
        "type": "content_block_delta",
        "index": index,
        "delta": {"type": "input_json_delta", "partial_json": partial_json},
    }
    return f"event: content_block_delta\ndata: {json.dumps(data)}\n\n"


def _make_block_stop_event(index: int) -> str:
    """Build Anthropic content_block_stop at a given index."""
    data = {"type": "content_block_stop", "index": index}
    return f"event: content_block_stop\ndata: {json.dumps(data)}\n\n"


def _make_message_delta_event(stop_reason: str = "end_turn") -> str:
    """Build the Anthropic message_delta SSE event string."""
    data = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": 0},
    }
    return f"event: message_delta\ndata: {json.dumps(data)}\n\n"


def _make_message_stop_event() -> str:
    """Build the Anthropic message_stop SSE event string."""
    data = {"type": "message_stop"}
    return f"event: message_stop\ndata: {json.dumps(data)}\n\n"


async def stream_codex_response(
    request_data: Dict[str, Any],
    model: str,
) -> AsyncGenerator[str, None]:
    """
    Stream a Codex response translated to Anthropic SSE format.

    Fetches a valid OAuth token, builds the Codex payload, opens a streaming
    POST to the Codex endpoint, and translates each SSE event to the Anthropic
    streaming format expected by Claude Code.

    Supports both text and tool_use responses.

    Args:
        request_data: Anthropic request as a plain dict (model_dump() output)
        model: Model name (e.g. "gpt-5.4")

    Yields:
        Anthropic-format SSE event strings

    Raises:
        HTTPException: On authentication, rate-limit, or server errors
    """
    # Obtain a valid token (refreshes automatically if expired)
    try:
        token = await get_codex_token()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "type": "error",
                "error": {
                    "type": "service_unavailable",
                    "message": (
                        "Codex CLI not authenticated. "
                        "Run `codex` to sign in."
                    ),
                },
            },
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=401,
            detail={
                "type": "error",
                "error": {
                    "type": "authentication_error",
                    "message": str(e),
                },
            },
        ) from e

    system_prompt = await get_codex_system_prompt()
    payload = _build_codex_payload(request_data, model, system_prompt)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }

    logger.info(f"Sending request to Codex endpoint (model={model})")
    logger.debug(f"Codex payload keys: {list(payload.keys())}, tools={len(payload.get('tools', []))}")

    message_id = f"msg_{uuid.uuid4().hex[:24]}"

    # Emit Anthropic stream-opening event
    yield _make_message_start_event(model, message_id)

    # State tracking for content blocks
    block_index = 0
    text_block_started = False
    has_tool_calls = False
    current_tool_index: Optional[int] = None

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=300, write=30, pool=30)) as client:
            async with client.stream("POST", _CODEX_URL, json=payload, headers=headers) as response:
                if response.status_code == 401:
                    await response.aread()
                    raise HTTPException(
                        status_code=401,
                        detail={
                            "type": "error",
                            "error": {
                                "type": "authentication_error",
                                "message": (
                                    "Codex token expired or invalid. "
                                    "Run `codex` to re-authenticate."
                                ),
                            },
                        },
                    )

                if response.status_code == 429:
                    await response.aread()
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "type": "error",
                            "error": {
                                "type": "rate_limit_error",
                                "message": (
                                    "Codex rate limit reached. "
                                    "You have hit the ChatGPT usage limit. "
                                    "Please wait before retrying."
                                ),
                            },
                        },
                    )

                if response.status_code >= 400:
                    try:
                        body = await response.aread()
                        detail_text = body.decode("utf-8", errors="replace")
                    except Exception:
                        detail_text = f"HTTP {response.status_code}"

                    logger.error(
                        f"Codex endpoint returned HTTP {response.status_code}: "
                        f"{detail_text[:200]}"
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail={
                            "type": "error",
                            "error": {
                                "type": "api_error",
                                "message": (
                                    f"Codex API error (HTTP {response.status_code}): "
                                    f"{detail_text[:200]}"
                                ),
                            },
                        },
                    )

                # Parse SSE stream from Codex and translate to Anthropic format
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue

                    raw = line[len("data: "):]
                    if raw.strip() in ("", "[DONE]"):
                        continue

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.debug(f"Codex SSE: skipping non-JSON line: {raw[:80]}")
                        continue

                    event_type = event.get("type", "")

                    # --- Text content ---
                    if event_type == "response.output_text.delta":
                        delta_text = event.get("delta", "")
                        if delta_text:
                            if not text_block_started:
                                yield _make_text_block_start_event(block_index)
                                text_block_started = True
                            yield _make_text_delta_event(block_index, delta_text)

                    elif event_type == "response.output_text.done":
                        # Text output complete — close text block if open
                        if text_block_started:
                            yield _make_block_stop_event(block_index)
                            block_index += 1
                            text_block_started = False

                    # --- Tool calls ---
                    elif event_type == "response.output_item.added":
                        item = event.get("item", {})
                        if item.get("type") == "function_call":
                            has_tool_calls = True
                            # Close text block if still open
                            if text_block_started:
                                yield _make_block_stop_event(block_index)
                                block_index += 1
                                text_block_started = False

                            tool_name = item.get("name", "")
                            call_id = item.get("call_id", f"toolu_{uuid.uuid4().hex[:24]}")
                            current_tool_index = block_index

                            logger.debug(f"Tool call started: {tool_name} (call_id={call_id})")
                            yield _make_tool_use_block_start_event(block_index, call_id, tool_name)

                    elif event_type == "response.function_call_arguments.delta":
                        delta = event.get("delta", "")
                        if delta and current_tool_index is not None:
                            yield _make_tool_input_delta_event(current_tool_index, delta)

                    elif event_type == "response.function_call_arguments.done":
                        if current_tool_index is not None:
                            yield _make_block_stop_event(current_tool_index)
                            block_index += 1
                            current_tool_index = None

                    elif event_type == "response.output_item.done":
                        item = event.get("item", {})
                        if item.get("type") == "function_call" and current_tool_index is not None:
                            # If arguments.done wasn't sent, close the block here
                            yield _make_block_stop_event(current_tool_index)
                            block_index += 1
                            current_tool_index = None

                    elif event_type == "response.completed":
                        logger.debug("Codex stream completed")

    except HTTPException:
        raise
    except httpx.TimeoutException as e:
        logger.error(f"Codex request timed out: {e}")
        raise HTTPException(
            status_code=504,
            detail={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": "Codex request timed out. Please try again.",
                },
            },
        ) from e
    except httpx.RequestError as e:
        logger.error(f"Codex network error: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": f"Could not reach Codex endpoint: {e}",
                },
            },
        ) from e

    # Close any open text block
    if text_block_started:
        yield _make_block_stop_event(block_index)

    # If no blocks were emitted at all, emit an empty text block
    if block_index == 0 and not text_block_started and not has_tool_calls:
        yield _make_text_block_start_event(0)
        yield _make_block_stop_event(0)

    # Emit Anthropic stream-closing events
    stop_reason = "tool_use" if has_tool_calls else "end_turn"
    yield _make_message_delta_event(stop_reason)
    yield _make_message_stop_event()
