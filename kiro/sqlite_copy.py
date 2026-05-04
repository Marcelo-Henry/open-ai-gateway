"""
SQLite database copy manager.

Copies the kiro-cli SQLite database to a working location so the gateway
and kiro-cli don't compete for locks on the same file.

Optimized to avoid re-copying the full database (~1 GB+) on every token
refresh.  The heavy copy happens once (on first boot); subsequent credential
reloads read the original DB in read-only mode and update only the in-memory
state.
"""

import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from kiro.config import SQLITE_COPY_DIR


def _get_copy_filename(source_path: str) -> str:
    """Generate a deterministic filename from the source path hash.

    Args:
        source_path: Path to the original SQLite database.

    Returns:
        Filename in the format kiro-db-<hash>.sqlite3.
    """
    normalized = str(Path(source_path).expanduser().resolve())
    path_hash = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"kiro-db-{path_hash}.sqlite3"


def get_working_db_path(source_path: str) -> str:
    """Return the working copy path for a given source without copying.

    Args:
        source_path: Path to the original SQLite database.

    Returns:
        Absolute path where the working copy would be stored.
    """
    return str(Path(SQLITE_COPY_DIR) / _get_copy_filename(source_path))


def copy_sqlite_db(source_path: str) -> str:
    """Copy the source SQLite DB to the working location.

    Uses shutil.copy2 which preserves metadata. Safe for SQLite files
    that are not being actively written to (kiro-cli writes are
    infrequent and atomic).

    Args:
        source_path: Path to the original SQLite database.

    Returns:
        Absolute path to the working copy.

    Raises:
        FileNotFoundError: If source does not exist.
        OSError: If copy fails.
    """
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"SQLite source not found: {source_path}")

    copy_dir = Path(SQLITE_COPY_DIR)
    copy_dir.mkdir(parents=True, exist_ok=True)

    dest = copy_dir / _get_copy_filename(source_path)
    shutil.copy2(str(source), str(dest))

    logger.info(f"SQLite DB copied: {source} -> {dest}")
    return str(dest)


def copy_if_missing(source_path: str) -> str:
    """Copy the source SQLite DB only if the working copy does not exist yet.

    On first boot the full copy is created.  On subsequent starts the
    existing copy is reused, avoiding a multi-second copy of large
    databases (~1 GB+).

    Args:
        source_path: Path to the original SQLite database.

    Returns:
        Absolute path to the working copy.

    Raises:
        FileNotFoundError: If source does not exist and no copy is available.
        OSError: If copy fails.
    """
    dest = get_working_db_path(source_path)
    if Path(dest).exists():
        logger.debug(f"SQLite working copy already exists, skipping copy: {dest}")
        return dest
    return copy_sqlite_db(source_path)


def read_credentials_from_source(
    source_path: str,
    token_keys: List[str],
    registration_keys: List[str],
) -> Dict[str, Any]:
    """Read credentials directly from the original SQLite DB in read-only mode.

    Opens the database with ``?mode=ro`` so no locks are acquired and the
    file is never modified.  This is used instead of re-copying the entire
    database when the gateway needs to pick up fresh tokens that kiro-cli
    may have written.

    Args:
        source_path: Path to the original kiro-cli SQLite database.
        token_keys: Ordered list of ``auth_kv`` keys to search for tokens.
        registration_keys: Ordered list of ``auth_kv`` keys for device
            registration (client_id / client_secret).

    Returns:
        Dict with credential fields found (may be empty).  Possible keys:
        ``access_token``, ``refresh_token``, ``expires_at``, ``region``,
        ``scopes``, ``client_id``, ``client_secret``, ``profile_arn``,
        ``detected_api_region``, ``sqlite_token_key``.

    Raises:
        FileNotFoundError: If source does not exist.
    """
    source = Path(source_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"SQLite source not found: {source_path}")

    result: Dict[str, Any] = {}

    uri = f"file:{source}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        cursor = conn.cursor()

        # --- token data ---
        for key in token_keys:
            cursor.execute("SELECT value FROM auth_kv WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                result["sqlite_token_key"] = key
                token_data = json.loads(row[0])
                if token_data.get("access_token"):
                    result["access_token"] = token_data["access_token"]
                if token_data.get("refresh_token"):
                    result["refresh_token"] = token_data["refresh_token"]
                if token_data.get("profile_arn"):
                    result["profile_arn"] = token_data["profile_arn"]
                if token_data.get("region"):
                    result["region"] = token_data["region"]
                if token_data.get("scopes"):
                    result["scopes"] = token_data["scopes"]
                if token_data.get("expires_at"):
                    result["expires_at"] = _parse_expires_at(token_data["expires_at"])
                break

        # --- device registration ---
        for key in registration_keys:
            cursor.execute("SELECT value FROM auth_kv WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                reg_data = json.loads(row[0])
                if reg_data.get("client_id"):
                    result["client_id"] = reg_data["client_id"]
                if reg_data.get("client_secret"):
                    result["client_secret"] = reg_data["client_secret"]
                if reg_data.get("region") and "region" not in result:
                    result["region"] = reg_data["region"]
                break

        # --- API region from profile ARN ---
        try:
            cursor.execute(
                "SELECT value FROM state WHERE key = 'api.codewhisperer.profile'"
            )
            profile_row = cursor.fetchone()
            if profile_row:
                profile_data = json.loads(profile_row[0])
                arn = profile_data.get("arn", "")
                if arn:
                    parts = arn.split(":")
                    if len(parts) >= 4 and re.match(r"^[a-z]+-[a-z]+-\d+$", parts[3]):
                        result["detected_api_region"] = parts[3]
        except sqlite3.Error:
            pass

    finally:
        conn.close()

    return result


def _parse_expires_at(expires_str: str) -> Optional[datetime]:
    """Parse an ISO-8601 / RFC-3339 expiration timestamp.

    Handles the nanosecond precision that kiro-cli writes (Python's
    ``fromisoformat`` only supports up to microseconds).

    Args:
        expires_str: Timestamp string.

    Returns:
        Parsed datetime or None on failure.
    """
    try:
        if expires_str.endswith("Z"):
            expires_str = expires_str.replace("Z", "+00:00")
        expires_str = re.sub(r"(\.\d{6})\d+", r"\1", expires_str)
        return datetime.fromisoformat(expires_str)
    except Exception as e:
        logger.warning(f"Failed to parse expires_at: {e}")
        return None
