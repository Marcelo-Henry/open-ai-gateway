
"""
Converters for transforming Gemini API format to Kiro format.

This module is an adapter layer that converts Gemini-specific formats
to the unified format used by converters_core.py.

Reference: https://ai.google.dev/api/generate-content
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from loguru import logger

from kiro.config import HIDDEN_MODELS
from kiro.model_resolver import get_model_id_for_kiro
from kiro.models_gemini import (
    GeminiContent,
    GeminiGenerateContentRequest,
    GeminiTool,
)
from kiro.converters_core import (
    UnifiedMessage,
    UnifiedTool,
    ThinkingConfig,
    build_kiro_payload,
)


def _extract_part_text(part: Any) -> str:
    """
    Extract text from a single Gemini part.

    Args:
        part: A Gemini part (dict or Pydantic model).

    Returns:
        Text string, or empty string if the part has no text.
    """
    if isinstance(part, dict):
        return part.get("text", "")
    if hasattr(part, "text"):
        return part.text
    return ""


def _get_part_type(part: Any) -> str:
    """
    Determine the type of a Gemini part.

    Returns one of: 'text', 'functionCall', 'functionResponse', 'inlineData', 'unknown'.

    Args:
        part: A Gemini part (dict or Pydantic model).

    Returns:
        String identifying the part type.
    """
    if isinstance(part, dict):
        if "text" in part:
            return "text"
        if "functionCall" in part:
            return "functionCall"
        if "functionResponse" in part:
            return "functionResponse"
        if "inlineData" in part:
            return "inlineData"
        return "unknown"

    # Pydantic model variants
    if hasattr(part, "text"):
        return "text"
    if hasattr(part, "functionCall"):
        return "functionCall"
    if hasattr(part, "functionResponse"):
        return "functionResponse"
    if hasattr(part, "inlineData"):
        return "inlineData"
    return "unknown"


def _get_part_data(part: Any, field: str) -> Any:
    """
    Extract a named field from a Gemini part.

    Args:
        part: A Gemini part (dict or Pydantic model).
        field: Field name to extract.

    Returns:
        Field value, or None if not present.
    """
    if isinstance(part, dict):
        return part.get(field)
    return getattr(part, field, None)


def convert_gemini_content_to_unified(content: GeminiContent) -> UnifiedMessage:
    """
    Convert a single GeminiContent block to a UnifiedMessage.

    Handles all part types:
    - text → content string
    - functionCall → tool_calls list
    - functionResponse → tool_results list
    - inlineData → images list

    Role mapping:
    - 'user' or None → 'user'
    - 'model' → 'assistant'

    Args:
        content: A GeminiContent block from the request.

    Returns:
        UnifiedMessage in the internal format.
    """
    # Map Gemini roles to unified roles
    gemini_role = content.role or "user"
    if gemini_role == "model":
        role = "assistant"
    else:
        role = "user"

    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    images: List[Dict[str, Any]] = []

    for part in content.parts:
        part_type = _get_part_type(part)

        if part_type == "text":
            text = _extract_part_text(part)
            if text:
                text_parts.append(text)

        elif part_type == "functionCall":
            fc_data = _get_part_data(part, "functionCall")
            if isinstance(fc_data, dict):
                name = fc_data.get("name", "")
                args = fc_data.get("args", {})
                call_id = f"call_{uuid.uuid4().hex[:16]}"
                tool_calls.append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps(args) if isinstance(args, dict) else str(args),
                    },
                })
                logger.debug(f"Converted functionCall part: name={name}")

        elif part_type == "functionResponse":
            fr_data = _get_part_data(part, "functionResponse")
            if isinstance(fr_data, dict):
                name = fr_data.get("name", "")
                response = fr_data.get("response", {})
                # Generate a stable tool_use_id from the function name
                tool_use_id = f"call_{uuid.uuid4().hex[:16]}"
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": json.dumps(response) if isinstance(response, dict) else str(response),
                })
                logger.debug(f"Converted functionResponse part: name={name}")

        elif part_type == "inlineData":
            inline = _get_part_data(part, "inlineData")
            if isinstance(inline, dict):
                mime_type = inline.get("mimeType", "image/jpeg")
                data = inline.get("data", "")
                if data:
                    images.append({"media_type": mime_type, "data": data})
                    logger.debug(f"Converted inlineData part: mimeType={mime_type}")

        else:
            logger.debug(f"Skipping unknown Gemini part type: {part_type}")

    return UnifiedMessage(
        role=role,
        content="".join(text_parts),
        tool_calls=tool_calls if tool_calls else None,
        tool_results=tool_results if tool_results else None,
        images=images if images else None,
    )


def convert_gemini_messages(contents: List[GeminiContent]) -> List[UnifiedMessage]:
    """
    Convert a list of GeminiContent blocks to UnifiedMessages.

    Args:
        contents: List of GeminiContent blocks from the request.

    Returns:
        List of UnifiedMessages in the internal format.
    """
    unified = [convert_gemini_content_to_unified(c) for c in contents]
    logger.debug(f"Converted {len(contents)} Gemini content blocks to unified messages")
    return unified


def convert_gemini_tools(tools: Optional[List[GeminiTool]]) -> Optional[List[UnifiedTool]]:
    """
    Convert Gemini tool definitions to UnifiedTool format.

    Args:
        tools: List of GeminiTool objects, or None.

    Returns:
        List of UnifiedTool objects, or None if no tools provided.
    """
    if not tools:
        return None

    unified_tools: List[UnifiedTool] = []
    for gemini_tool in tools:
        declarations = None
        if isinstance(gemini_tool, dict):
            declarations = gemini_tool.get("functionDeclarations")
        else:
            declarations = gemini_tool.functionDeclarations

        if not declarations:
            continue

        for decl in declarations:
            if isinstance(decl, dict):
                name = decl.get("name", "")
                description = decl.get("description")
                parameters = decl.get("parameters")
            else:
                name = decl.name
                description = decl.description
                parameters = decl.parameters

            unified_tools.append(
                UnifiedTool(
                    name=name,
                    description=description,
                    input_schema=parameters,
                )
            )

    return unified_tools if unified_tools else None


def extract_gemini_system_prompt(system_instruction: Optional[GeminiContent]) -> str:
    """
    Extract system prompt text from a Gemini systemInstruction block.

    Args:
        system_instruction: Optional GeminiContent with system instructions.

    Returns:
        System prompt as a plain string, or empty string if not provided.
    """
    if system_instruction is None:
        return ""

    parts = system_instruction.parts if hasattr(system_instruction, "parts") else []
    text_parts = []
    for part in parts:
        text = _extract_part_text(part)
        if text:
            text_parts.append(text)

    return "\n".join(text_parts)


def gemini_to_kiro(
    request: GeminiGenerateContentRequest,
    model_name: str,
    conversation_id: str,
    profile_arn: str = "",
) -> Dict[str, Any]:
    """
    Convert a Gemini generateContent request to a Kiro API payload dict.

    This is the main entry point for Gemini → Kiro conversion.

    Key differences from OpenAI/Anthropic:
    - Roles are 'user' / 'model' (not 'user' / 'assistant')
    - Tool calls use 'functionCall' parts (not separate tool_calls field)
    - Tool results use 'functionResponse' parts (not tool_result blocks)
    - System prompt is a separate 'systemInstruction' field

    Thinking is disabled for Gemini input path — Gemini clients do not
    expect <thinking> tags in responses.

    Args:
        request: GeminiGenerateContentRequest from the client.
        model_name: Model name as provided in the URL path parameter.
        conversation_id: Unique conversation ID for Kiro API.
        profile_arn: AWS CodeWhisperer profile ARN (optional).

    Returns:
        Payload dictionary ready for POST to Kiro generateAssistantResponse API.

    Raises:
        ValueError: If there are no messages to send.
    """
    # Convert messages to unified format
    unified_messages = convert_gemini_messages(request.contents)

    # Convert tools to unified format
    unified_tools = convert_gemini_tools(request.tools)

    # Extract system prompt from systemInstruction field
    system_prompt = extract_gemini_system_prompt(request.systemInstruction)

    # Resolve model ID for Kiro API
    model_id = get_model_id_for_kiro(model_name, HIDDEN_MODELS)

    # Gemini clients don't expect thinking tags — disable fake reasoning
    thinking_config = ThinkingConfig(enabled=False)

    logger.debug(
        f"Converting Gemini request: model={model_name} -> {model_id}, "
        f"messages={len(unified_messages)}, "
        f"tools={len(unified_tools) if unified_tools else 0}, "
        f"system_prompt_length={len(system_prompt)}"
    )

    result = build_kiro_payload(
        messages=unified_messages,
        system_prompt=system_prompt,
        model_id=model_id,
        tools=unified_tools,
        conversation_id=conversation_id,
        profile_arn=profile_arn,
        thinking_config=thinking_config,
    )

    return result.payload
