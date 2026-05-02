
"""
Streaming logic for converting Kiro stream to Gemini API format.

This module formats Kiro events into Gemini generateContent response format:
- Non-streaming: single GeminiGenerateContentResponse JSON dict
- Streaming: SSE lines with plain 'data: {...}' format (no 'event:' prefix)

Gemini streaming SSE format differs from Anthropic/OpenAI:
- No 'event:' prefix lines
- Each chunk is a complete (partial) GeminiGenerateContentResponse
- Final chunk includes finishReason and usageMetadata

Reference: https://ai.google.dev/api/generate-content#v1beta.GenerateContentResponse
"""

import json
import uuid
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

import httpx
from loguru import logger

from kiro.streaming_core import (
    collect_stream_to_result,
    parse_kiro_stream,
    KiroEvent,
)
from kiro.tokenizer import count_tokens

if TYPE_CHECKING:
    from kiro.auth import KiroAuthManager
    from kiro.cache import ModelInfoCache


# ==================================================================================================
# Finish Reason Mapping
# ==================================================================================================

_FINISH_REASON_MAP: Dict[str, str] = {
    "end_turn": "STOP",
    "tool_use": "STOP",
    "max_tokens": "MAX_TOKENS",
    "stop_sequence": "STOP",
}


def _map_finish_reason(kiro_reason: Optional[str]) -> str:
    """
    Map a Kiro/Anthropic stop reason to a Gemini finishReason string.

    Args:
        kiro_reason: Stop reason from Kiro stream (e.g., 'end_turn', 'max_tokens').

    Returns:
        Gemini finishReason string (e.g., 'STOP', 'MAX_TOKENS').
    """
    if not kiro_reason:
        return "STOP"
    return _FINISH_REASON_MAP.get(kiro_reason, "STOP")


# ==================================================================================================
# Non-Streaming Response Collection
# ==================================================================================================


async def collect_gemini_response(
    response: httpx.Response,
    model_name: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[List[Dict[str, Any]]] = None,
    request_tools: Optional[List[Dict[str, Any]]] = None,
    request_system: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Collect a full Kiro stream and return it as a Gemini generateContent response.

    Used for non-streaming mode (POST /v1beta/models/{model}:generateContent).

    Args:
        response: HTTP response with Kiro SSE stream.
        model_name: Model name to include in the response.
        model_cache: Model metadata cache (unused currently, reserved for future use).
        auth_manager: Authentication manager (unused currently, reserved for future use).
        request_messages: Original request messages (for token counting).
        request_tools: Original request tools (for token counting).
        request_system: Original system prompt (for token counting).

    Returns:
        Dict matching GeminiGenerateContentResponse schema.
    """
    result = await collect_stream_to_result(response)

    parts: List[Dict[str, Any]] = []

    # Add text content if present
    if result.content:
        parts.append({"text": result.content})

    # Add tool call parts
    for tc in result.tool_calls:
        func = tc.get("function", {})
        name = func.get("name", "") or tc.get("name", "")
        arguments = func.get("arguments", {}) or tc.get("input", {})

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {}

        parts.append({
            "functionCall": {
                "name": name,
                "args": arguments,
            }
        })

    # Determine finish reason
    if result.tool_calls:
        finish_reason = "STOP"
    else:
        finish_reason = "STOP"

    # Token counting
    output_tokens = count_tokens(result.content)
    prompt_tokens = 0

    candidate = {
        "content": {
            "role": "model",
            "parts": parts if parts else [{"text": ""}],
        },
        "finishReason": finish_reason,
        "index": 0,
    }

    usage_metadata = {
        "promptTokenCount": prompt_tokens,
        "candidatesTokenCount": output_tokens,
        "totalTokenCount": prompt_tokens + output_tokens,
    }

    logger.debug(
        f"[Gemini Non-Streaming] Completed: "
        f"output_tokens={output_tokens}, tool_calls={len(result.tool_calls)}, "
        f"finish_reason={finish_reason}"
    )

    return {
        "candidates": [candidate],
        "usageMetadata": usage_metadata,
        "modelVersion": model_name,
    }


# ==================================================================================================
# Streaming Response
# ==================================================================================================


async def stream_kiro_to_gemini(
    response: httpx.Response,
    model_name: str,
    model_cache: "ModelInfoCache",
    auth_manager: "KiroAuthManager",
    request_messages: Optional[List[Dict[str, Any]]] = None,
    request_tools: Optional[List[Dict[str, Any]]] = None,
    request_system: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Stream Kiro response as Gemini SSE format.

    Converts Kiro SSE events to Gemini streaming format. Each chunk is a
    plain 'data: {...}' line (no 'event:' prefix — Gemini uses plain data lines).

    Gemini streaming format per chunk:
        data: {"candidates": [{"content": {"role": "model", "parts": [{"text": "..."}]}, "finishReason": ""}]}

    Final chunk includes finishReason and usageMetadata:
        data: {"candidates": [{"content": {"role": "model", "parts": []}, "finishReason": "STOP"}], "usageMetadata": {...}}

    Args:
        response: HTTP response with Kiro SSE stream.
        model_name: Model name to include in the response.
        model_cache: Model metadata cache (reserved for future use).
        auth_manager: Authentication manager (reserved for future use).
        request_messages: Original request messages (for token counting).
        request_tools: Original request tools (for token counting).
        request_system: Original system prompt (for token counting).

    Yields:
        Strings in Gemini SSE format (each ending with double newline).

    Raises:
        Exception: Propagates stream parsing errors to the caller.
    """
    accumulated_content = ""
    accumulated_tool_calls: List[Dict[str, Any]] = []
    finish_reason: Optional[str] = None
    context_usage_percentage: Optional[float] = None

    try:
        async for event in parse_kiro_stream(response):
            if event.type == "content" and event.content:
                accumulated_content += event.content
                chunk = _build_text_chunk(event.content, finish_reason="")
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            elif event.type == "tool_use" and event.tool_use:
                accumulated_tool_calls.append(event.tool_use)
                # Emit tool call as functionCall part
                tc = event.tool_use
                func = tc.get("function", {})
                name = func.get("name", "") or tc.get("name", "")
                arguments = func.get("arguments", {}) or tc.get("input", {})

                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                chunk = _build_function_call_chunk(name, arguments, finish_reason="")
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            elif event.type == "context_usage":
                context_usage_percentage = event.context_usage_percentage

            elif event.type == "error":
                logger.error(f"Kiro stream error event: {event}")

        # Determine final finish reason
        if accumulated_tool_calls:
            finish_reason = "STOP"
        else:
            finish_reason = "STOP"

        # Calculate token counts
        output_tokens = count_tokens(accumulated_content)
        prompt_tokens = 0

        usage_metadata = {
            "promptTokenCount": prompt_tokens,
            "candidatesTokenCount": output_tokens,
            "totalTokenCount": prompt_tokens + output_tokens,
        }

        # Emit final chunk with finishReason and usageMetadata
        final_chunk = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [],
                    },
                    "finishReason": finish_reason,
                    "index": 0,
                }
            ],
            "usageMetadata": usage_metadata,
            "modelVersion": model_name,
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"

        logger.debug(
            f"[Gemini Streaming] Completed: "
            f"output_tokens={output_tokens}, tool_calls={len(accumulated_tool_calls)}, "
            f"finish_reason={finish_reason}"
        )

    except GeneratorExit:
        logger.debug("Client disconnected during Gemini streaming (GeneratorExit)")
        raise
    except Exception as e:
        logger.error(f"Error during Gemini stream conversion: {e}", exc_info=True)
        raise
    finally:
        try:
            await response.aclose()
        except Exception as close_error:
            logger.debug(f"Error closing response: {close_error}")


# ==================================================================================================
# Chunk Builders
# ==================================================================================================


def _build_text_chunk(text: str, finish_reason: str = "") -> Dict[str, Any]:
    """
    Build a Gemini streaming chunk for text content.

    Args:
        text: Text content to include in the chunk.
        finish_reason: Finish reason string (empty string for intermediate chunks).

    Returns:
        Dict matching partial GeminiGenerateContentResponse schema.
    """
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": text}],
                },
                "finishReason": finish_reason,
                "index": 0,
            }
        ]
    }


def _build_function_call_chunk(
    name: str, args: Dict[str, Any], finish_reason: str = ""
) -> Dict[str, Any]:
    """
    Build a Gemini streaming chunk for a function call.

    Args:
        name: Function name.
        args: Function arguments dict.
        finish_reason: Finish reason string (empty string for intermediate chunks).

    Returns:
        Dict matching partial GeminiGenerateContentResponse schema.
    """
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": name,
                                "args": args,
                            }
                        }
                    ],
                },
                "finishReason": finish_reason,
                "index": 0,
            }
        ]
    }
