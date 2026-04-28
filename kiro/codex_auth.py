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
Codex CLI OAuth token management.

Reads credentials from the Codex CLI auth file (~/.codex/auth.json),
checks expiry, refreshes when needed, and returns a valid access token.

The auth file is created automatically by the Codex CLI after `codex` login.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from loguru import logger

from kiro.config import CODEX_AUTH_FILE, CODEX_ENABLED

# Refresh endpoint for OpenAI OAuth tokens
_OPENAI_REFRESH_URL = "https://auth.openai.com/oauth/token"

# Seconds before expiry to trigger a proactive refresh
_REFRESH_THRESHOLD_MS = 60 * 1000  # 1 minute in milliseconds

# In-memory token cache (avoids re-reading the file on every request)
_cached_token: Optional[str] = None
_cached_expires_ms: Optional[float] = None

# Lock prevents concurrent refresh races
_refresh_lock = asyncio.Lock()


def _resolve_auth_path() -> Path:
    """
    Resolve the Codex auth file path, expanding ~ and env vars.

    Returns:
        Resolved Path object
    """
    return Path(CODEX_AUTH_FILE).expanduser().resolve()


def is_codex_available() -> bool:
    """
    Check whether Codex auth is configured and the auth file exists.

    Does NOT validate the token — only checks file presence.
    Safe to call at startup without network access.

    Returns:
        True if CODEX_ENABLED and auth file exists and is readable
    """
    if not CODEX_ENABLED:
        return False
    path = _resolve_auth_path()
    return path.exists() and path.is_file()


def _read_auth_file() -> Dict[str, Any]:
    """
    Read and parse the Codex auth JSON file.

    Returns:
        Parsed JSON dict

    Raises:
        FileNotFoundError: If auth file does not exist
        ValueError: If file content is not valid JSON or missing required fields
    """
    path = _resolve_auth_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Codex auth file not found: {path}\n"
            "Run `codex` to sign in and create the auth file."
        )

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise FileNotFoundError(
            f"Cannot read Codex auth file {path}: {e}\n"
            "Check file permissions or run `codex` to re-authenticate."
        ) from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Codex auth file {path} contains invalid JSON: {e}\n"
            "Run `codex` to re-authenticate and recreate the file."
        ) from e

    if not isinstance(data, dict):
        raise ValueError(
            f"Codex auth file {path} must contain a JSON object, got {type(data).__name__}.\n"
            "Run `codex` to re-authenticate."
        )

    return data


def _save_auth_file(data: Dict[str, Any]) -> None:
    """
    Write updated auth data back to the auth file.

    Args:
        data: Auth data dict to persist

    Raises:
        OSError: If the file cannot be written
    """
    path = _resolve_auth_path()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Codex auth file updated with refreshed token")
    except OSError as e:
        # Non-fatal: we still have the new token in memory
        logger.warning(f"Could not save refreshed Codex token to {path}: {e}")


def _is_token_expired(expires_ms: Optional[float]) -> bool:
    """
    Check whether a token is expired or about to expire.

    Args:
        expires_ms: Expiry timestamp in milliseconds, or None

    Returns:
        True if expired or expiry is unknown
    """
    if expires_ms is None:
        return False
    now_ms = time.time() * 1000
    return now_ms >= (expires_ms - _REFRESH_THRESHOLD_MS)


async def _refresh_token(refresh_token: str) -> Dict[str, Any]:
    """
    Exchange a refresh token for a new access token via OpenAI OAuth.

    Args:
        refresh_token: The refresh token from the auth file

    Returns:
        Dict with at least 'access_token' and optionally 'expires_in'

    Raises:
        httpx.HTTPStatusError: On non-2xx response
        ValueError: If response is missing expected fields
    """
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    logger.debug("Refreshing Codex OAuth token...")

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(_OPENAI_REFRESH_URL, json=payload)
        response.raise_for_status()
        data = response.json()

    if "access_token" not in data:
        raise ValueError(
            f"Codex token refresh response missing 'access_token': {list(data.keys())}"
        )

    logger.info("Codex OAuth token refreshed successfully")
    return data


async def get_codex_token() -> str:
    """
    Return a valid Codex access token, refreshing if necessary.

    Uses an in-memory cache to avoid re-reading the file on every request.
    Uses an asyncio.Lock to prevent concurrent refresh races.

    Returns:
        Valid access token string

    Raises:
        FileNotFoundError: If auth file does not exist
        ValueError: If auth file is malformed or refresh fails
        RuntimeError: If token is expired and refresh is not possible
    """
    global _cached_token, _cached_expires_ms

    async with _refresh_lock:
        # Fast path: cached token is still valid
        if _cached_token and not _is_token_expired(_cached_expires_ms):
            logger.debug("Using cached Codex token (still valid)")
            return _cached_token

        # Read auth file
        auth_data = _read_auth_file()

        tokens_dict = auth_data.get("tokens", auth_data)
        access_token: Optional[str] = tokens_dict.get("access_token")
        refresh_token: Optional[str] = tokens_dict.get("refresh_token")
        expires_ms: Optional[float] = tokens_dict.get("expires")  # milliseconds

        if not access_token:
            raise ValueError(
                "Codex auth file is missing 'access_token'.\n"
                "Run `codex` to re-authenticate."
            )

        # Token is still valid — update cache and return
        if not _is_token_expired(expires_ms):
            _cached_token = access_token
            _cached_expires_ms = expires_ms
            logger.debug("Codex token loaded from file (still valid)")
            return access_token

        # Token is expired — attempt refresh
        if not refresh_token:
            raise RuntimeError(
                "Codex token is expired and no refresh_token is available.\n"
                "Run `codex` to re-authenticate."
            )

        try:
            refreshed = await _refresh_token(refresh_token)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Codex token refresh failed (HTTP {e.response.status_code}).\n"
                "Run `codex` to re-authenticate."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Codex token refresh failed: {e}\n"
                "Run `codex` to re-authenticate."
            ) from e

        new_access_token: str = refreshed["access_token"]
        new_refresh_token: Optional[str] = refreshed.get("refresh_token", refresh_token)
        expires_in_sec: Optional[int] = refreshed.get("expires_in")

        # Compute new expiry in milliseconds
        new_expires_ms: Optional[float] = None
        if expires_in_sec is not None:
            new_expires_ms = (time.time() + expires_in_sec) * 1000

        # Persist refreshed token back to file
        auth_data["access_token"] = new_access_token
        if new_refresh_token:
            auth_data["refresh_token"] = new_refresh_token
        if new_expires_ms is not None:
            auth_data["expires"] = new_expires_ms
        _save_auth_file(auth_data)

        # Update in-memory cache
        _cached_token = new_access_token
        _cached_expires_ms = new_expires_ms

        return new_access_token


def clear_token_cache() -> None:
    """
    Clear the in-memory token cache.

    Useful in tests to reset state between test cases.
    """
    global _cached_token, _cached_expires_ms
    _cached_token = None
    _cached_expires_ms = None
