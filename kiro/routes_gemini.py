
"""
FastAPI routes for Gemini Generative Language API v1beta.

Contains endpoints compatible with Google's Gemini API:
- POST /v1beta/models/{model_id}:generateContent
- POST /v1beta/models/{model_id}:streamGenerateContent
- GET  /v1beta/models
- GET  /v1beta/models/{model_id}

Reference: https://ai.google.dev/api/generate-content
"""

import json
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from loguru import logger

from kiro.config import PROXY_API_KEY, HIDDEN_MODELS, FALLBACK_MODELS
from kiro.models_gemini import (
    GeminiGenerateContentRequest,
    GeminiGenerateContentResponse,
    GeminiModelInfo,
    GeminiModelsListResponse,
)
from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.converters_gemini import gemini_to_kiro
from kiro.streaming_gemini import collect_gemini_response, stream_kiro_to_gemini
from kiro.http_client import KiroHttpClient
from kiro.utils import generate_conversation_id

# Import debug_logger
try:
    from kiro.debug_logger import debug_logger
except ImportError:
    debug_logger = None


# ==================================================================================================
# Authentication
# ==================================================================================================

# Gemini CLI sends auth via x-goog-api-key header
gemini_api_key_header = APIKeyHeader(name="x-goog-api-key", auto_error=False)
# Also support Authorization: Bearer for compatibility
auth_header = APIKeyHeader(name="Authorization", auto_error=False)


async def verify_gemini_api_key(
    x_goog_api_key: Optional[str] = Security(gemini_api_key_header),
    authorization: Optional[str] = Security(auth_header),
) -> bool:
    """
    Verify API key for Gemini API.

    Supports two authentication methods:
    1. x-goog-api-key header (Gemini native)
    2. Authorization: Bearer header (for compatibility)

    Args:
        x_goog_api_key: Value from x-goog-api-key header.
        authorization: Value from Authorization header.

    Returns:
        True if key is valid.

    Raises:
        HTTPException: 401 with Gemini error format if key is invalid or missing.
    """
    # Check x-goog-api-key first (Gemini native)
    if x_goog_api_key and x_goog_api_key == PROXY_API_KEY:
        return True

    # Fall back to Authorization: Bearer
    if authorization and authorization == f"Bearer {PROXY_API_KEY}":
        return True

    logger.warning("Access attempt with invalid API key (Gemini endpoint)")
    raise HTTPException(
        status_code=401,
        detail=gemini_error_detail(401, "Invalid or missing API key. Use x-goog-api-key header or Authorization: Bearer."),
    )


# ==================================================================================================
# Error Helpers
# ==================================================================================================

_STATUS_MAP = {
    400: "INVALID_ARGUMENT",
    401: "UNAUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    429: "RESOURCE_EXHAUSTED",
    500: "INTERNAL",
    503: "UNAVAILABLE",
}


def gemini_error_detail(status_code: int, message: str) -> dict:
    """
    Build a Gemini-format error detail dict.

    Args:
        status_code: HTTP status code.
        message: Human-readable error message.

    Returns:
        Dict with Gemini error structure: {"error": {"code": ..., "message": ..., "status": ...}}.
    """
    status_str = _STATUS_MAP.get(status_code, "INTERNAL")
    return {
        "error": {
            "code": status_code,
            "message": message,
            "status": status_str,
        }
    }


def gemini_error_response(status_code: int, message: str) -> JSONResponse:
    """
    Build a JSONResponse with Gemini-format error body.

    Args:
        status_code: HTTP status code.
        message: Human-readable error message.

    Returns:
        JSONResponse with Gemini error format.
    """
    return JSONResponse(
        status_code=status_code,
        content=gemini_error_detail(status_code, message),
    )


# ==================================================================================================
# Model List Helpers
# ==================================================================================================

# Hardcoded Gemini model names to expose in /v1beta/models
_GEMINI_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

_SUPPORTED_METHODS = ["generateContent", "streamGenerateContent"]


def _build_model_info(model_id: str) -> GeminiModelInfo:
    """
    Build a GeminiModelInfo object for a given model ID.

    Args:
        model_id: Model identifier (without 'models/' prefix).

    Returns:
        GeminiModelInfo with name, displayName, and supportedGenerationMethods.
    """
    display_name = model_id.replace("-", " ").title()
    return GeminiModelInfo(
        name=f"models/{model_id}",
        displayName=display_name,
        supportedGenerationMethods=_SUPPORTED_METHODS,
    )


def _strip_models_prefix(model_id: str) -> str:
    """
    Strip 'models/' prefix from a model ID if present.

    Args:
        model_id: Model ID, possibly prefixed with 'models/'.

    Returns:
        Model ID without the 'models/' prefix.
    """
    if model_id.startswith("models/"):
        return model_id[len("models/"):]
    return model_id


# ==================================================================================================
# Router
# ==================================================================================================

router = APIRouter(tags=["Gemini API"])


# ==================================================================================================
# Model List Endpoints
# ==================================================================================================


@router.get("/v1beta/models", dependencies=[Depends(verify_gemini_api_key)])
async def list_models(request: Request) -> JSONResponse:
    """
    List available models in Gemini format.

    Returns all models from the model cache (filtered to gemini-* prefix)
    plus the hardcoded Gemini model list.

    Args:
        request: FastAPI Request for accessing app.state.

    Returns:
        JSONResponse with GeminiModelsListResponse schema.
    """
    model_ids: list = list(_GEMINI_MODELS)

    # Also include any gemini-* models from the dynamic cache
    try:
        account = request.app.state.account_manager.get_first_account()
        if account and account.model_cache:
            cached_ids = account.model_cache.get_all_model_ids()
            for mid in cached_ids:
                if mid.startswith("gemini-") and mid not in model_ids:
                    model_ids.append(mid)
    except Exception as e:
        logger.debug(f"Could not fetch models from cache for Gemini list: {e}")

    models = [_build_model_info(mid) for mid in model_ids]
    response_data = GeminiModelsListResponse(models=models)
    return JSONResponse(content=response_data.model_dump())


@router.get("/v1beta/models/{model_id:path}", dependencies=[Depends(verify_gemini_api_key)])
async def get_model(model_id: str) -> JSONResponse:
    """
    Get information about a specific model.

    Args:
        model_id: Model ID, possibly prefixed with 'models/'.

    Returns:
        JSONResponse with GeminiModelInfo schema.
    """
    clean_id = _strip_models_prefix(model_id)
    model_info = _build_model_info(clean_id)
    return JSONResponse(content=model_info.model_dump())


# ==================================================================================================
# Generate Content Endpoints
# ==================================================================================================


@router.post(
    "/v1beta/models/{model_id:path}:generateContent",
    dependencies=[Depends(verify_gemini_api_key)],
)
async def generate_content(
    model_id: str,
    request: Request,
    request_data: GeminiGenerateContentRequest,
) -> JSONResponse:
    """
    Gemini generateContent endpoint (non-streaming).

    Compatible with Google's POST /v1beta/models/{model}:generateContent.
    Accepts requests in Gemini format and translates them to Kiro API.

    Required headers:
    - x-goog-api-key: Your API key (or Authorization: Bearer)
    - Content-Type: application/json

    Args:
        model_id: Model ID from URL path (e.g., 'gemini-2.5-pro' or 'models/gemini-2.5-pro').
        request: FastAPI Request for accessing app.state.
        request_data: Request in GeminiGenerateContentRequest format.

    Returns:
        JSONResponse with GeminiGenerateContentResponse schema.

    Raises:
        HTTPException: On validation or API errors.
    """
    clean_model = _strip_models_prefix(model_id)
    logger.info(f"Request to /v1beta/models/{clean_model}:generateContent (non-streaming)")

    return await _handle_generate_content(
        request=request,
        request_data=request_data,
        model_name=clean_model,
        streaming=False,
    )


@router.post(
    "/v1beta/models/{model_id:path}:streamGenerateContent",
    dependencies=[Depends(verify_gemini_api_key)],
)
async def stream_generate_content(
    model_id: str,
    request: Request,
    request_data: GeminiGenerateContentRequest,
) -> StreamingResponse:
    """
    Gemini streamGenerateContent endpoint (streaming).

    Compatible with Google's POST /v1beta/models/{model}:streamGenerateContent.
    Returns a streaming response in Gemini SSE format.

    Gemini SSE format uses plain 'data: {...}' lines without 'event:' prefix.

    Required headers:
    - x-goog-api-key: Your API key (or Authorization: Bearer)
    - Content-Type: application/json

    Args:
        model_id: Model ID from URL path.
        request: FastAPI Request for accessing app.state.
        request_data: Request in GeminiGenerateContentRequest format.

    Returns:
        StreamingResponse with media_type='text/event-stream'.

    Raises:
        HTTPException: On validation or API errors.
    """
    clean_model = _strip_models_prefix(model_id)
    logger.info(f"Request to /v1beta/models/{clean_model}:streamGenerateContent (streaming)")

    return await _handle_generate_content(
        request=request,
        request_data=request_data,
        model_name=clean_model,
        streaming=True,
    )


# ==================================================================================================
# Shared Handler
# ==================================================================================================


async def _handle_generate_content(
    request: Request,
    request_data: GeminiGenerateContentRequest,
    model_name: str,
    streaming: bool,
):
    """
    Shared handler for both generateContent and streamGenerateContent.

    Follows the EXACT same account system failover vs legacy mode pattern
    as routes_anthropic.py.

    Args:
        request: FastAPI Request for accessing app.state.
        request_data: Parsed GeminiGenerateContentRequest.
        model_name: Resolved model name (without 'models/' prefix).
        streaming: True for streaming mode, False for non-streaming.

    Returns:
        JSONResponse (non-streaming) or StreamingResponse (streaming).
    """
    if request.app.state.account_system:
        # ==============================================================================
        # ACCOUNT SYSTEM ENABLED: Failover Loop
        # ==============================================================================
        from kiro.account_errors import classify_error, ErrorType

        account_manager = request.app.state.account_manager
        all_accounts = list(account_manager._accounts.keys())
        MAX_ATTEMPTS = len(all_accounts) * 2

        last_error_message = None
        last_error_status = None
        tried_accounts = set()

        for attempt in range(MAX_ATTEMPTS):
            account = await account_manager.get_next_account(
                model_name,
                exclude_accounts=tried_accounts,
            )

            if account is None:
                if len(all_accounts) == 1:
                    return gemini_error_response(
                        last_error_status or 503,
                        last_error_message or "Account unavailable",
                    )
                else:
                    detail = "No available accounts for this model."
                    if last_error_message:
                        detail += f" Last error: {last_error_message}"
                    return gemini_error_response(503, detail)

            tried_accounts.add(account.id)
            auth_manager = account.auth_manager
            model_cache = account.model_cache

            conversation_id = generate_conversation_id()
            profile_arn_for_payload = ""
            if auth_manager.auth_type == AuthType.KIRO_DESKTOP and auth_manager.profile_arn:
                profile_arn_for_payload = auth_manager.profile_arn

            try:
                kiro_payload = gemini_to_kiro(
                    request_data,
                    model_name,
                    conversation_id,
                    profile_arn_for_payload,
                )
            except ValueError as e:
                logger.error(f"Gemini conversion error: {e}")
                return gemini_error_response(400, str(e))

            url = f"{auth_manager.api_host}/generateAssistantResponse"
            logger.debug(f"Kiro API URL: {url} (account: {account.id})")

            if streaming:
                http_client = KiroHttpClient(auth_manager, shared_client=None)
            else:
                shared_client = request.app.state.http_client
                http_client = KiroHttpClient(auth_manager, shared_client=shared_client)

            try:
                response = await http_client.request_with_retry(
                    "POST", url, kiro_payload, stream=True
                )

                if response.status_code == 200:
                    await account_manager.report_success(account.id, model_name)

                    if streaming:
                        async def stream_wrapper_account():
                            try:
                                async for chunk in stream_kiro_to_gemini(
                                    response=response,
                                    model_name=model_name,
                                    model_cache=model_cache,
                                    auth_manager=auth_manager,
                                ):
                                    yield chunk
                            except GeneratorExit:
                                logger.debug("Client disconnected (Gemini streaming)")
                            except Exception as e:
                                logger.error(f"Gemini streaming error: {e}", exc_info=True)
                            finally:
                                await http_client.close()

                        return StreamingResponse(
                            stream_wrapper_account(),
                            media_type="text/event-stream",
                            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
                        )
                    else:
                        gemini_response = await collect_gemini_response(
                            response=response,
                            model_name=model_name,
                            model_cache=model_cache,
                            auth_manager=auth_manager,
                        )
                        await http_client.close()
                        logger.info(f"HTTP 200 - Gemini generateContent (non-streaming) - completed")
                        return JSONResponse(content=gemini_response)

                else:
                    try:
                        error_content = await response.aread()
                    except Exception:
                        error_content = b"Unknown error"

                    await http_client.close()
                    error_text = error_content.decode("utf-8", errors="replace")

                    error_reason = None
                    try:
                        error_json = json.loads(error_text)
                        from kiro.kiro_errors import enhance_kiro_error
                        error_info = enhance_kiro_error(error_json)
                        error_reason = error_info.reason
                        last_error_message = error_info.user_message
                        last_error_status = response.status_code
                    except (json.JSONDecodeError, KeyError):
                        last_error_message = error_text
                        last_error_status = response.status_code

                    error_type = classify_error(response.status_code, error_reason)

                    if error_type == ErrorType.FATAL:
                        await account_manager.report_failure(
                            account.id, model_name, error_type,
                            response.status_code, error_reason,
                        )
                        logger.warning(f"HTTP {response.status_code} - Gemini - {last_error_message[:100]}")
                        return gemini_error_response(response.status_code, last_error_message)
                    else:
                        await account_manager.report_failure(
                            account.id, model_name, error_type,
                            response.status_code, error_reason,
                        )
                        if len(all_accounts) == 1:
                            break
                        continue

            except HTTPException as e:
                await http_client.close()
                if e.status_code in (502, 504):
                    await account_manager.report_failure(
                        account.id, model_name, ErrorType.RECOVERABLE,
                        e.status_code, None,
                    )
                    last_error_message = str(e.detail)
                    last_error_status = e.status_code
                    if len(all_accounts) == 1:
                        break
                    logger.warning(f"Network error on account {account.id}, trying next account")
                    continue
                logger.error(f"HTTP {e.status_code} - Gemini - {e.detail}")
                raise
            except Exception as e:
                await http_client.close()
                logger.error(f"Internal error (Gemini): {e}", exc_info=True)
                return gemini_error_response(500, f"Internal Server Error: {str(e)}")

        # All attempts exhausted
        if len(all_accounts) == 1:
            return gemini_error_response(
                last_error_status or 503,
                last_error_message or "Account unavailable",
            )
        else:
            detail = "All accounts failed after full circle."
            if last_error_message:
                detail += f" Last error: {last_error_message}"
            return gemini_error_response(503, detail)

    else:
        # ==============================================================================
        # LEGACY MODE: Single Account (no failover)
        # ==============================================================================
        account = request.app.state.account_manager.get_first_account()
        if not account.auth_manager:
            logger.error("No initialized accounts available (Gemini legacy mode)")
            return gemini_error_response(503, "No initialized accounts available")

        auth_manager = account.auth_manager
        model_cache = account.model_cache

    # ==============================================================================
    # Normal Flow (legacy mode continues here)
    # ==============================================================================

    conversation_id = generate_conversation_id()
    profile_arn_for_payload = ""
    if auth_manager.auth_type == AuthType.KIRO_DESKTOP and auth_manager.profile_arn:
        profile_arn_for_payload = auth_manager.profile_arn

    try:
        kiro_payload = gemini_to_kiro(
            request_data,
            model_name,
            conversation_id,
            profile_arn_for_payload,
        )
    except ValueError as e:
        logger.error(f"Gemini conversion error: {e}")
        return gemini_error_response(400, str(e))

    # Log Kiro payload
    try:
        kiro_request_body = json.dumps(kiro_payload, ensure_ascii=False, indent=2).encode("utf-8")
        if debug_logger:
            debug_logger.log_kiro_request_body(kiro_request_body)
    except Exception as e:
        logger.warning(f"Failed to log Kiro request: {e}")

    url = f"{auth_manager.api_host}/generateAssistantResponse"
    logger.debug(f"Kiro API URL: {url}")

    if streaming:
        http_client = KiroHttpClient(auth_manager, shared_client=None)
    else:
        shared_client = request.app.state.http_client
        http_client = KiroHttpClient(auth_manager, shared_client=shared_client)

    try:
        response = await http_client.request_with_retry(
            "POST", url, kiro_payload, stream=True
        )

        if response.status_code != 200:
            try:
                error_content = await response.aread()
            except Exception:
                error_content = b"Unknown error"

            await http_client.close()
            error_text = error_content.decode("utf-8", errors="replace")

            error_message = error_text
            try:
                error_json = json.loads(error_text)
                from kiro.kiro_errors import enhance_kiro_error
                error_info = enhance_kiro_error(error_json)
                error_message = error_info.user_message
                logger.debug(f"Original Kiro error: {error_info.original_message} (reason: {error_info.reason})")
            except (json.JSONDecodeError, KeyError):
                pass

            logger.warning(f"HTTP {response.status_code} - Gemini - {error_message[:100]}")

            if debug_logger:
                debug_logger.flush_on_error(response.status_code, error_message)

            return gemini_error_response(response.status_code, error_message)

        if streaming:
            async def stream_wrapper():
                streaming_error = None
                client_disconnected = False
                try:
                    async for chunk in stream_kiro_to_gemini(
                        response=response,
                        model_name=model_name,
                        model_cache=model_cache,
                        auth_manager=auth_manager,
                    ):
                        yield chunk
                except GeneratorExit:
                    client_disconnected = True
                    logger.debug("Client disconnected during Gemini streaming (GeneratorExit)")
                except Exception as e:
                    streaming_error = e
                    logger.error(f"Gemini streaming error: {e}", exc_info=True)
                finally:
                    await http_client.close()
                    if streaming_error:
                        error_type = type(streaming_error).__name__
                        error_msg = str(streaming_error) if str(streaming_error) else "(empty message)"
                        logger.error(f"HTTP 500 - Gemini streamGenerateContent - [{error_type}] {error_msg[:100]}")
                    elif client_disconnected:
                        logger.info("HTTP 200 - Gemini streamGenerateContent - client disconnected")
                    else:
                        logger.info("HTTP 200 - Gemini streamGenerateContent - completed")

                    if debug_logger:
                        if streaming_error:
                            debug_logger.flush_on_error(500, str(streaming_error))
                        else:
                            debug_logger.discard_buffers()

            return StreamingResponse(
                stream_wrapper(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
            )

        else:
            gemini_response = await collect_gemini_response(
                response=response,
                model_name=model_name,
                model_cache=model_cache,
                auth_manager=auth_manager,
            )
            await http_client.close()
            logger.info("HTTP 200 - Gemini generateContent (non-streaming) - completed")

            if debug_logger:
                debug_logger.discard_buffers()

            return JSONResponse(content=gemini_response)

    except HTTPException as e:
        await http_client.close()
        if e.status_code in (502, 504):
            logger.warning("Network error (Gemini legacy mode, no failover available)")
        logger.error(f"HTTP {e.status_code} - Gemini - {e.detail}")
        if debug_logger:
            debug_logger.flush_on_error(e.status_code, str(e.detail))
        raise
    except Exception as e:
        await http_client.close()
        logger.error(f"Internal error (Gemini): {e}", exc_info=True)
        logger.error(f"HTTP 500 - Gemini - {str(e)[:100]}")
        if debug_logger:
            debug_logger.flush_on_error(500, str(e))
        return gemini_error_response(500, f"Internal Server Error: {str(e)}")
