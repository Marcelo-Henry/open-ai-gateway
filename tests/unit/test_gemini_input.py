"""
Unit tests for Gemini API support.

Tests cover:
- models_gemini.py: Pydantic model parsing and validation
- converters_gemini.py: Gemini request → UnifiedMessage/UnifiedTool conversion
- streaming_gemini.py: Kiro stream → Gemini response format
- routes_gemini.py: FastAPI endpoint authentication and basic behavior

All tests are completely isolated from the network.
"""

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.models_gemini import (
    GeminiContent,
    GeminiFunctionCallPart,
    GeminiFunctionDeclaration,
    GeminiFunctionResponsePart,
    GeminiGenerateContentRequest,
    GeminiGenerationConfig,
    GeminiInlineDataPart,
    GeminiTextPart,
    GeminiTool,
)
from kiro.converters_gemini import (
    convert_gemini_content_to_unified,
    convert_gemini_messages,
    convert_gemini_tools,
    extract_gemini_system_prompt,
    gemini_to_kiro,
)
from kiro.streaming_core import KiroEvent
import kiro.streaming_gemini as streaming_gemini
from kiro.streaming_gemini import (
    collect_gemini_response,
    stream_kiro_to_gemini,
)
from kiro.routes_gemini import router as gemini_router
from kiro.config import PROXY_API_KEY


# ==================================================================================================
# Shared Fixtures
# ==================================================================================================


class DummyResponse:
    """Minimal mock for httpx.Response used in streaming tests."""

    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class DummyModelCache:
    """Minimal mock for ModelInfoCache."""

    def get_max_input_tokens(self, model: str) -> int:
        return 200000

    def get_all_model_ids(self):
        return []


class DummyAuthManager:
    """Minimal mock for KiroAuthManager."""

    api_host = "https://q.us-east-1.amazonaws.com"
    profile_arn = ""

    class auth_type:
        pass


class DummyAccount:
    """Minimal mock for an account object."""

    def __init__(self):
        self.auth_manager = DummyAuthManager()
        self.model_cache = DummyModelCache()
        self.id = "test-account"


class DummyAccountManager:
    """Minimal mock for AccountManager."""

    def get_first_account(self):
        return DummyAccount()

    @property
    def _accounts(self):
        return {"test-account": DummyAccount()}


def _make_test_app() -> FastAPI:
    """
    Build a minimal FastAPI app with the Gemini router and mocked state.

    Returns:
        FastAPI app with Gemini router and mock account_manager.
    """
    app = FastAPI()
    app.include_router(gemini_router)

    # Attach mock state
    app.state.account_system = False
    app.state.account_manager = DummyAccountManager()
    app.state.http_client = MagicMock()

    return app


# ==================================================================================================
# TestGeminiModels
# ==================================================================================================


class TestGeminiModels:
    """Tests for Pydantic models in models_gemini.py."""

    def test_generate_content_request_valid(self):
        """Valid request with user text parses correctly."""
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": "Hello, world!"}]}
            ]
        }
        req = GeminiGenerateContentRequest(**data)
        assert len(req.contents) == 1
        assert req.contents[0].role == "user"
        assert len(req.contents[0].parts) == 1

    def test_generate_content_request_with_tools(self):
        """Request with functionDeclarations parses correctly."""
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": "What is the weather?"}]}
            ],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "get_weather",
                            "description": "Get current weather",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "city": {"type": "string"}
                                },
                                "required": ["city"],
                            },
                        }
                    ]
                }
            ],
        }
        req = GeminiGenerateContentRequest(**data)
        assert req.tools is not None
        assert len(req.tools) == 1
        decls = req.tools[0].functionDeclarations
        assert decls is not None
        assert decls[0].name == "get_weather"

    def test_generate_content_request_extra_fields_allowed(self):
        """Extra fields in the request do not raise a validation error."""
        data = {
            "contents": [
                {"role": "user", "parts": [{"text": "Hi"}]}
            ],
            "safetySettings": [{"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}],
            "unknownFutureField": "some_value",
        }
        # Should not raise
        req = GeminiGenerateContentRequest(**data)
        assert len(req.contents) == 1

    def test_generation_config_optional_fields(self):
        """GeminiGenerationConfig accepts partial fields."""
        config = GeminiGenerationConfig(temperature=0.7, maxOutputTokens=1024)
        assert config.temperature == 0.7
        assert config.maxOutputTokens == 1024
        assert config.topP is None

    def test_system_instruction_parsed(self):
        """systemInstruction field parses as GeminiContent."""
        data = {
            "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
            "systemInstruction": {
                "parts": [{"text": "You are a helpful assistant."}]
            },
        }
        req = GeminiGenerateContentRequest(**data)
        assert req.systemInstruction is not None
        assert len(req.systemInstruction.parts) == 1


# ==================================================================================================
# TestConvertersGemini
# ==================================================================================================


class TestConvertersGemini:
    """Tests for converters_gemini.py."""

    def test_simple_user_message(self):
        """User text content converts to UnifiedMessage with role='user'."""
        content = GeminiContent(role="user", parts=[{"text": "Hello"}])
        msg = convert_gemini_content_to_unified(content)
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.tool_calls is None
        assert msg.tool_results is None

    def test_model_role_becomes_assistant(self):
        """Gemini 'model' role maps to 'assistant' in unified format."""
        content = GeminiContent(role="model", parts=[{"text": "I can help."}])
        msg = convert_gemini_content_to_unified(content)
        assert msg.role == "assistant"
        assert msg.content == "I can help."

    def test_none_role_treated_as_user(self):
        """Content with no role defaults to 'user'."""
        content = GeminiContent(role=None, parts=[{"text": "Question"}])
        msg = convert_gemini_content_to_unified(content)
        assert msg.role == "user"

    def test_function_call_part_becomes_tool_call(self):
        """functionCall part converts to tool_calls list."""
        content = GeminiContent(
            role="model",
            parts=[
                {
                    "functionCall": {
                        "name": "get_weather",
                        "args": {"city": "NYC"},
                    }
                }
            ],
        )
        msg = convert_gemini_content_to_unified(content)
        assert msg.role == "assistant"
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 1
        tc = msg.tool_calls[0]
        assert tc["function"]["name"] == "get_weather"
        # arguments should be JSON-serializable
        args = json.loads(tc["function"]["arguments"])
        assert args == {"city": "NYC"}

    def test_function_response_part_becomes_tool_result(self):
        """functionResponse part converts to tool_results list."""
        content = GeminiContent(
            role="user",
            parts=[
                {
                    "functionResponse": {
                        "name": "get_weather",
                        "response": {"temperature": "72F", "condition": "sunny"},
                    }
                }
            ],
        )
        msg = convert_gemini_content_to_unified(content)
        assert msg.role == "user"
        assert msg.tool_results is not None
        assert len(msg.tool_results) == 1
        tr = msg.tool_results[0]
        assert tr["type"] == "tool_result"
        assert "tool_use_id" in tr
        # content should be JSON string of the response
        parsed = json.loads(tr["content"])
        assert parsed["temperature"] == "72F"

    def test_system_instruction_extracted(self):
        """systemInstruction.parts[0].text becomes the system prompt."""
        system = GeminiContent(
            role=None,
            parts=[{"text": "You are a helpful assistant."}],
        )
        result = extract_gemini_system_prompt(system)
        assert result == "You are a helpful assistant."

    def test_system_instruction_none_returns_empty(self):
        """None systemInstruction returns empty string."""
        result = extract_gemini_system_prompt(None)
        assert result == ""

    def test_tools_converted_to_unified(self):
        """functionDeclarations convert to UnifiedTool list."""
        tools = [
            GeminiTool(
                functionDeclarations=[
                    GeminiFunctionDeclaration(
                        name="search",
                        description="Search the web",
                        parameters={
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    )
                ]
            )
        ]
        unified = convert_gemini_tools(tools)
        assert unified is not None
        assert len(unified) == 1
        assert unified[0].name == "search"
        assert unified[0].description == "Search the web"
        assert unified[0].input_schema is not None

    def test_tools_none_returns_none(self):
        """None tools input returns None."""
        result = convert_gemini_tools(None)
        assert result is None

    def test_tools_empty_list_returns_none(self):
        """Empty tools list returns None."""
        result = convert_gemini_tools([])
        assert result is None

    def test_inline_data_becomes_image(self):
        """inlineData part converts to images list."""
        content = GeminiContent(
            role="user",
            parts=[
                {"text": "What is in this image?"},
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": "abc123base64data",
                    }
                },
            ],
        )
        msg = convert_gemini_content_to_unified(content)
        assert msg.images is not None
        assert len(msg.images) == 1
        assert msg.images[0]["media_type"] == "image/png"
        assert msg.images[0]["data"] == "abc123base64data"
        # Text part should still be captured
        assert msg.content == "What is in this image?"

    def test_multiple_text_parts_concatenated(self):
        """Multiple text parts in one content block are concatenated."""
        content = GeminiContent(
            role="user",
            parts=[{"text": "Hello "}, {"text": "world"}],
        )
        msg = convert_gemini_content_to_unified(content)
        assert msg.content == "Hello world"

    def test_gemini_to_kiro_calls_build_payload(self):
        """gemini_to_kiro returns a dict with conversationState key."""
        request = GeminiGenerateContentRequest(
            contents=[
                GeminiContent(role="user", parts=[{"text": "Hello"}])
            ]
        )
        with patch("kiro.converters_gemini.get_model_id_for_kiro", return_value="claude-sonnet-4.5"):
            payload = gemini_to_kiro(
                request=request,
                model_name="gemini-2.5-pro",
                conversation_id="test-conv-id",
                profile_arn="",
            )
        assert "conversationState" in payload
        assert payload["conversationState"]["conversationId"] == "test-conv-id"


# ==================================================================================================
# TestStreamingGemini
# ==================================================================================================


class TestStreamingGemini:
    """Tests for streaming_gemini.py."""

    @pytest.mark.asyncio
    async def test_collect_response_text(self, monkeypatch):
        """Text response from Kiro stream produces correct Gemini JSON."""

        async def fake_collect(response, **kwargs):
            from kiro.streaming_core import StreamResult
            result = StreamResult()
            result.content = "Hello from Gemini"
            result.tool_calls = []
            return result

        monkeypatch.setattr(streaming_gemini, "collect_stream_to_result", fake_collect)

        response = DummyResponse()
        result = await collect_gemini_response(
            response=response,
            model_name="gemini-2.5-pro",
            model_cache=DummyModelCache(),
            auth_manager=DummyAuthManager(),
        )

        assert "candidates" in result
        assert len(result["candidates"]) == 1
        candidate = result["candidates"][0]
        assert candidate["content"]["role"] == "model"
        parts = candidate["content"]["parts"]
        assert any(p.get("text") == "Hello from Gemini" for p in parts)
        assert candidate["finishReason"] == "STOP"
        assert "usageMetadata" in result
        assert result["modelVersion"] == "gemini-2.5-pro"

    @pytest.mark.asyncio
    async def test_collect_response_with_tool_call(self, monkeypatch):
        """Tool call in Kiro stream produces functionCall part in Gemini response."""

        async def fake_collect(response, **kwargs):
            from kiro.streaming_core import StreamResult
            result = StreamResult()
            result.content = ""
            result.tool_calls = [
                {
                    "id": "call_abc",
                    "function": {
                        "name": "get_weather",
                        "arguments": json.dumps({"city": "NYC"}),
                    },
                }
            ]
            return result

        monkeypatch.setattr(streaming_gemini, "collect_stream_to_result", fake_collect)

        response = DummyResponse()
        result = await collect_gemini_response(
            response=response,
            model_name="gemini-2.5-pro",
            model_cache=DummyModelCache(),
            auth_manager=DummyAuthManager(),
        )

        candidate = result["candidates"][0]
        parts = candidate["content"]["parts"]
        fc_parts = [p for p in parts if "functionCall" in p]
        assert len(fc_parts) == 1
        assert fc_parts[0]["functionCall"]["name"] == "get_weather"
        assert fc_parts[0]["functionCall"]["args"] == {"city": "NYC"}

    @pytest.mark.asyncio
    async def test_stream_emits_data_lines(self, monkeypatch):
        """Streaming produces 'data: {...}' lines without 'event:' prefix."""

        async def fake_parse_kiro_stream(response, **kwargs):
            yield KiroEvent(type="content", content="Hello")
            yield KiroEvent(type="content", content=" world")

        monkeypatch.setattr(streaming_gemini, "parse_kiro_stream", fake_parse_kiro_stream)

        response = DummyResponse()
        chunks = []
        async for chunk in stream_kiro_to_gemini(
            response=response,
            model_name="gemini-2.5-pro",
            model_cache=DummyModelCache(),
            auth_manager=DummyAuthManager(),
        ):
            chunks.append(chunk)

        # All chunks must start with 'data: ' and NOT contain 'event:'
        for chunk in chunks:
            assert chunk.startswith("data: "), f"Chunk does not start with 'data: ': {chunk!r}"
            assert "event:" not in chunk, f"Chunk contains 'event:' prefix: {chunk!r}"

        # Each chunk must be valid JSON after stripping 'data: '
        for chunk in chunks:
            stripped = chunk.strip()
            assert stripped.startswith("data: ")
            json.loads(stripped[6:])  # Should not raise

    @pytest.mark.asyncio
    async def test_stream_final_chunk_has_finish_reason(self, monkeypatch):
        """Last streaming chunk contains finishReason='STOP' and usageMetadata."""

        async def fake_parse_kiro_stream(response, **kwargs):
            yield KiroEvent(type="content", content="Answer")
            yield KiroEvent(type="context_usage", context_usage_percentage=5.0)

        monkeypatch.setattr(streaming_gemini, "parse_kiro_stream", fake_parse_kiro_stream)

        response = DummyResponse()
        chunks = []
        async for chunk in stream_kiro_to_gemini(
            response=response,
            model_name="gemini-2.5-pro",
            model_cache=DummyModelCache(),
            auth_manager=DummyAuthManager(),
        ):
            chunks.append(chunk)

        # Last chunk should have finishReason and usageMetadata
        last_chunk = chunks[-1]
        data = json.loads(last_chunk.strip()[6:])  # strip 'data: '
        assert "candidates" in data
        candidate = data["candidates"][0]
        assert candidate["finishReason"] == "STOP"
        assert "usageMetadata" in data

    @pytest.mark.asyncio
    async def test_stream_tool_call_emits_function_call_part(self, monkeypatch):
        """Tool call event in stream produces functionCall part in SSE chunk."""

        async def fake_parse_kiro_stream(response, **kwargs):
            yield KiroEvent(
                type="tool_use",
                tool_use={
                    "id": "call_xyz",
                    "function": {
                        "name": "search",
                        "arguments": json.dumps({"query": "python"}),
                    },
                },
            )

        monkeypatch.setattr(streaming_gemini, "parse_kiro_stream", fake_parse_kiro_stream)

        response = DummyResponse()
        chunks = []
        async for chunk in stream_kiro_to_gemini(
            response=response,
            model_name="gemini-2.5-pro",
            model_cache=DummyModelCache(),
            auth_manager=DummyAuthManager(),
        ):
            chunks.append(chunk)

        # Find a chunk with functionCall
        fc_chunks = []
        for chunk in chunks:
            data = json.loads(chunk.strip()[6:])
            for candidate in data.get("candidates", []):
                for part in candidate.get("content", {}).get("parts", []):
                    if "functionCall" in part:
                        fc_chunks.append(part)

        assert len(fc_chunks) >= 1
        assert fc_chunks[0]["functionCall"]["name"] == "search"


# ==================================================================================================
# TestRoutesGemini
# ==================================================================================================


class TestRoutesGemini:
    """Tests for routes_gemini.py FastAPI endpoints."""

    def _make_client(self) -> TestClient:
        """Create a TestClient with the Gemini router and mocked state."""
        app = _make_test_app()
        return TestClient(app, raise_server_exceptions=False)

    def test_generate_content_requires_auth(self):
        """Request without API key returns 401 with Gemini error format."""
        client = self._make_client()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
        }
        response = client.post(
            "/v1beta/models/gemini-2.5-pro:generateContent",
            json=payload,
        )
        assert response.status_code == 401
        data = response.json()
        # FastAPI wraps HTTPException detail under "detail" key
        error_body = data.get("detail") or data
        assert "error" in error_body
        assert error_body["error"]["code"] == 401
        assert error_body["error"]["status"] == "UNAUTHENTICATED"

    def test_generate_content_invalid_key(self):
        """Request with wrong API key returns 401."""
        client = self._make_client()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
        }
        response = client.post(
            "/v1beta/models/gemini-2.5-pro:generateContent",
            json=payload,
            headers={"x-goog-api-key": "wrong-key"},
        )
        assert response.status_code == 401
        data = response.json()
        error_body = data.get("detail") or data
        assert "error" in error_body

    def test_generate_content_bearer_auth_invalid(self):
        """Request with wrong Bearer token returns 401."""
        client = self._make_client()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
        }
        response = client.post(
            "/v1beta/models/gemini-2.5-pro:generateContent",
            json=payload,
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert response.status_code == 401

    def test_models_list_returns_gemini_models(self):
        """GET /v1beta/models returns a list of models in Gemini format."""
        client = self._make_client()
        response = client.get(
            "/v1beta/models",
            headers={"x-goog-api-key": PROXY_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0
        # Each model should have the required fields
        for model in data["models"]:
            assert "name" in model
            assert model["name"].startswith("models/")
            assert "displayName" in model
            assert "supportedGenerationMethods" in model

    def test_get_single_model(self):
        """GET /v1beta/models/{model_id} returns model info."""
        client = self._make_client()
        response = client.get(
            "/v1beta/models/gemini-2.5-pro",
            headers={"x-goog-api-key": PROXY_API_KEY},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "models/gemini-2.5-pro"
        assert "supportedGenerationMethods" in data

    def test_stream_generate_content_requires_auth(self):
        """streamGenerateContent without API key returns 401."""
        client = self._make_client()
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
        }
        response = client.post(
            "/v1beta/models/gemini-2.5-pro:streamGenerateContent",
            json=payload,
        )
        assert response.status_code == 401

    def test_models_list_requires_auth(self):
        """GET /v1beta/models without API key returns 401."""
        client = self._make_client()
        response = client.get("/v1beta/models")
        assert response.status_code == 401

    def test_bearer_auth_accepted(self):
        """Authorization: Bearer header is accepted as valid auth."""
        client = self._make_client()
        # This will fail at the Kiro API call level (no real backend),
        # but should NOT fail at the auth level (should not be 401)
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
        }
        with patch("kiro.routes_gemini.KiroHttpClient") as mock_client_cls:
            mock_http = AsyncMock()
            mock_http.request_with_retry = AsyncMock(
                side_effect=Exception("No backend in test")
            )
            mock_http.close = AsyncMock()
            mock_client_cls.return_value = mock_http

            response = client.post(
                "/v1beta/models/gemini-2.5-pro:generateContent",
                json=payload,
                headers={"Authorization": f"Bearer {PROXY_API_KEY}"},
            )
        # Should not be 401 (auth passed), may be 500 due to mocked backend
        assert response.status_code != 401
