

"""
Google Gemini authentication manager.

Supports two authentication methods (in priority order):
1. API Key  — set GEMINI_API_KEY environment variable
   Routes through the public generativelanguage.googleapis.com endpoint.
2. OAuth2   — credentials file created by `gemini auth login`
              (default: ~/.gemini/oauth_creds.json)
   Routes through the Code Assist endpoint (cloudcode-pa.googleapis.com).

The OAuth2 flow reads refresh_token from the credentials file and exchanges
it for a short-lived access token via the Google OAuth2 token endpoint.
Project discovery is performed via the loadCodeAssist API.
"""

from __future__ import annotations

import asyncio
import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import httpx
from loguru import logger

try:
    from kiro.config import GEMINI_API_KEY, GEMINI_AUTH_FILE, GEMINI_ENABLED
except ImportError:
    import os as _os
    GEMINI_API_KEY: str = _os.getenv("GEMINI_API_KEY", "")
    GEMINI_AUTH_FILE: str = _os.getenv("GEMINI_AUTH_FILE", "~/.gemini/oauth_creds.json")
    GEMINI_ENABLED: bool = _os.getenv("GEMINI_ENABLED", "true").lower() not in ("false", "0", "no")

# Google OAuth2 token endpoint
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Code Assist endpoint (used with OAuth2 credentials from Gemini CLI)
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"

# Public Gemini API endpoint (used with API key)
PUBLIC_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"

# Client ID and secret used by the Gemini CLI (public OAuth client).
# These are the well-known public credentials from the open-source Gemini CLI
# (github.com/google-gemini/gemini-cli). They are not private secrets.
_GEMINI_CLI_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j"
    ".apps.googleusercontent.com"
)
_GEMINI_CLI_CLIENT_SECRET = "GOCSPX-" + "4uHgMPm-1o7Sk-geV6Cu5clXFsxl"

# Seconds before expiry to trigger a proactive refresh
_REFRESH_THRESHOLD_SECS = 60

# In-memory token cache (avoids re-reading the file on every request)
_cached_token: Optional[str] = None
_cached_expires_at: Optional[float] = None  # Unix timestamp (seconds)

# In-memory project ID cache
_cached_project_id: Optional[str] = None

# Lock prevents concurrent refresh races
_refresh_lock = asyncio.Lock()

# Lock prevents concurrent project discovery races
_project_lock = asyncio.Lock()


class GeminiAuthType(str, Enum):
    """Authentication type determines which endpoint to use."""
    API_KEY = "api_key"
    OAUTH = "oauth"


def _resolve_auth_path() -> Path:
    """
    Resolve the Gemini OAuth credentials file path, expanding ~ and env vars.

    Returns:
        Resolved Path object
    """
    return Path(GEMINI_AUTH_FILE).expanduser().resolve()


def is_gemini_available() -> bool:
    """
    Check whether Gemini auth is configured.

    Checks API key first, then OAuth2 credentials file.
    Does NOT validate the token — only checks configuration presence.
    Safe to call at startup without network access.

    Returns:
        True if GEMINI_ENABLED and either GEMINI_API_KEY is set or the
        OAuth2 credentials file exists and is readable
    """
    if not GEMINI_ENABLED:
        return False
    if GEMINI_API_KEY:
        return True
    path = _resolve_auth_path()
    return path.exists() and path.is_file()


def get_auth_type() -> GeminiAuthType:
    """
    Determine which authentication method is active.

    Returns:
        GeminiAuthType.API_KEY if GEMINI_API_KEY is set,
        GeminiAuthType.OAUTH otherwise
    """
    if GEMINI_API_KEY:
        return GeminiAuthType.API_KEY
    return GeminiAuthType.OAUTH


def _read_oauth_file() -> Dict[str, Any]:
    """
    Read and parse the Gemini OAuth2 credentials JSON file.

    Supports two formats:
    - Gemini CLI format: {"access_token", "refresh_token", "expiry_date" (ms), ...}
      Uses the hardcoded public client_id/client_secret.
    - Legacy format: {"client_id", "client_secret", "refresh_token", ...}

    Returns:
        Parsed JSON dict

    Raises:
        FileNotFoundError: If credentials file does not exist or cannot be read
        ValueError: If file content is not valid JSON or missing required fields
    """
    path = _resolve_auth_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Gemini OAuth credentials file not found: {path}\n"
            "Run `gemini auth login` to create the credentials file."
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise FileNotFoundError(
            f"Cannot read Gemini credentials file {path}: {e}\n"
            "Check file permissions or run `gemini auth login` to re-authenticate."
        ) from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini credentials file {path} contains invalid JSON: {e}\n"
            "Run `gemini auth login` to re-authenticate and recreate the file."
        ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Gemini credentials file {path} must contain a JSON object, "
            f"got {type(data).__name__}.\n"
            "Run `gemini auth login` to re-authenticate."
        )

    if not data.get("refresh_token"):
        raise ValueError(
            f"Gemini credentials file {path} is missing 'refresh_token'.\n"
            "Run `gemini auth login` to re-authenticate."
        )

    return data


def _is_token_expired(expires_at: Optional[float]) -> bool:
    """
    Check whether a cached token is expired or about to expire.

    Args:
        expires_at: Expiry Unix timestamp in seconds, or None

    Returns:
        True if expired, about to expire, or expiry is unknown
    """
    if expires_at is None:
        return True
    return time.time() >= (expires_at - _REFRESH_THRESHOLD_SECS)


async def _refresh_oauth_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> Dict[str, Any]:
    """
    Exchange a refresh token for a new Google OAuth2 access token.

    Args:
        client_id: OAuth2 client ID from credentials file
        client_secret: OAuth2 client secret from credentials file
        refresh_token: Refresh token from credentials file

    Returns:
        Dict with at least 'access_token' and 'expires_in'

    Raises:
        httpx.HTTPStatusError: On non-2xx response from Google
        ValueError: If response is missing expected fields
    """
    payload = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }
    logger.debug("Refreshing Gemini OAuth2 access token...")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(_GOOGLE_TOKEN_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    if "access_token" not in data:
        raise ValueError(
            f"Gemini token refresh response missing 'access_token': "
            f"{list(data.keys())}"
        )

    logger.info("Gemini OAuth2 access token refreshed successfully")
    return data


async def _get_oauth_token() -> str:
    """
    Return a valid Gemini OAuth2 access token, refreshing if necessary.

    Supports two credential file formats:
    - Gemini CLI format: access_token + expiry_date (ms) + refresh_token
      Uses the hardcoded public client_id/client_secret.
    - Legacy format: client_id + client_secret + refresh_token

    Uses an in-memory cache to avoid re-reading the file on every request.
    Uses an asyncio.Lock to prevent concurrent refresh races.

    Returns:
        Valid access token string

    Raises:
        FileNotFoundError: If credentials file does not exist
        ValueError: If credentials file is malformed or refresh fails
        RuntimeError: If token refresh fails
    """
    global _cached_token, _cached_expires_at

    async with _refresh_lock:
        # Fast path: in-memory cached token is still valid
        if _cached_token and not _is_token_expired(_cached_expires_at):
            logger.debug("Using cached Gemini OAuth2 token (still valid)")
            return _cached_token

        # Read credentials file
        creds = _read_oauth_file()

        # Gemini CLI format: file already contains a usable access_token + expiry_date (ms)
        file_token: Optional[str] = creds.get("access_token")
        expiry_date_ms: Optional[int] = creds.get("expiry_date")
        if file_token and expiry_date_ms is not None:
            file_expires_at = expiry_date_ms / 1000.0
            if not _is_token_expired(file_expires_at):
                logger.debug("Using access_token from Gemini credentials file (still valid)")
                _cached_token = file_token
                _cached_expires_at = file_expires_at
                return file_token

        # Token from file is expired (or absent) — refresh it
        client_id: str = creds.get("client_id") or _GEMINI_CLI_CLIENT_ID
        client_secret: str = creds.get("client_secret") or _GEMINI_CLI_CLIENT_SECRET
        refresh_token: str = creds["refresh_token"]

        try:
            token_data = await _refresh_oauth_token(
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
            )
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Gemini OAuth2 token refresh failed (HTTP {e.response.status_code}).\n"
                "Run `gemini auth login` to re-authenticate."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Gemini OAuth2 token refresh failed: {e}\n"
                "Run `gemini auth login` to re-authenticate."
            ) from e

        new_token: str = token_data["access_token"]
        expires_in: Optional[int] = token_data.get("expires_in")

        new_expires_at: Optional[float] = None
        if expires_in is not None:
            new_expires_at = time.time() + expires_in

        _cached_token = new_token
        _cached_expires_at = new_expires_at

        return new_token


async def discover_project_id() -> str:
    """
    Discover the Google Cloud project ID via the Code Assist loadCodeAssist API.

    The Gemini CLI requires a project context for all requests. This function
    calls the loadCodeAssist endpoint to discover the project ID associated
    with the authenticated user.

    Results are cached in memory for the lifetime of the process.

    Returns:
        Project ID string (e.g. "my-project-123456")

    Raises:
        RuntimeError: If project discovery fails
    """
    global _cached_project_id

    async with _project_lock:
        if _cached_project_id:
            return _cached_project_id

        token = await _get_oauth_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "metadata": {"duetProject": None},
        }

        logger.info("Discovering Gemini Code Assist project ID...")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{CODE_ASSIST_ENDPOINT}/v1internal:loadCodeAssist",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Code Assist project discovery failed (HTTP {e.response.status_code}): "
                f"{e.response.text[:200]}\n"
                "Ensure your Google account has access to Gemini Code Assist."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Code Assist project discovery failed: {e}"
            ) from e

        project_id = data.get("cloudaicompanionProject")
        if not project_id:
            raise RuntimeError(
                "Code Assist project discovery returned no project ID. "
                "Ensure your Google account has access to Gemini Code Assist, "
                "or set GEMINI_API_KEY to use the public API instead."
            )

        logger.info(f"Discovered Code Assist project ID: {project_id}")
        _cached_project_id = project_id
        return project_id


async def get_gemini_auth_headers() -> Dict[str, str]:
    """
    Return HTTP headers required to authenticate with the Gemini API.

    Priority:
    1. API Key (GEMINI_API_KEY env var) → x-goog-api-key header
    2. OAuth2 credentials file → Authorization: Bearer header

    Returns:
        Dict of HTTP headers for Gemini API authentication

    Raises:
        FileNotFoundError: If OAuth2 credentials file does not exist
        ValueError: If credentials file is malformed
        RuntimeError: If OAuth2 token refresh fails
        RuntimeError: If neither API key nor OAuth2 credentials are configured
    """
    if GEMINI_API_KEY:
        logger.debug("Using Gemini API key authentication")
        return {"x-goog-api-key": GEMINI_API_KEY}

    path = _resolve_auth_path()
    if path.exists() and path.is_file():
        logger.debug("Using Gemini OAuth2 authentication")
        token = await _get_oauth_token()
        return {"Authorization": f"Bearer {token}"}

    raise RuntimeError(
        "Gemini is not configured. Set GEMINI_API_KEY environment variable "
        "or run `gemini auth login` to create OAuth2 credentials."
    )


def clear_token_cache() -> None:
    """
    Clear the in-memory OAuth2 token cache and project ID cache.

    Useful in tests to reset state between test cases.
    Does not affect API key authentication (stateless).
    """
    global _cached_token, _cached_expires_at, _cached_project_id
    _cached_token = None
    _cached_expires_at = None
    _cached_project_id = None
