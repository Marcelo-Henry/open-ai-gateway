"""Integration tests for auth.py SQLite copy behavior."""

import json
import sqlite3
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro.auth import KiroAuthManager


def _create_auth_db(path: Path, access_token: str = "test-token-123", expires_at: str = "2099-01-01T00:00:00+00:00") -> None:
    """Create a SQLite database with auth_kv table mimicking kiro-cli."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
    token_data = json.dumps({
        "access_token": access_token,
        "refresh_token": "refresh-token-abc",
        "expires_at": expires_at,
        "region": "us-east-1",
        "startUrl": "https://example.com",
        "provider": "test",
    })
    conn.execute("INSERT INTO auth_kv (key, value) VALUES (?, ?)", ("kirocli:social:token", token_data))
    conn.commit()
    conn.close()


def _file_hash(path: Path) -> str:
    """SHA256 hash of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestAuthManagerSqliteCopy:
    """Tests for KiroAuthManager using SQLite copy."""

    def test_copies_sqlite_on_init(self, tmp_path: Path) -> None:
        """KiroAuthManager creates a copy and loads credentials from it."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            manager = KiroAuthManager(sqlite_db=str(source))

        assert manager._access_token == "test-token-123"
        assert manager._sqlite_db_source == str(source)
        assert manager._sqlite_db is not None
        assert manager._sqlite_db != str(source)
        assert Path(manager._sqlite_db).exists()

    def test_refresh_copy_picks_up_changes(self, tmp_path: Path) -> None:
        """After modifying the original, _refresh_sqlite_copy() loads the new token."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source, access_token="old-token")

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            manager = KiroAuthManager(sqlite_db=str(source))
            assert manager._access_token == "old-token"

            # Simulate kiro-cli updating the token
            conn = sqlite3.connect(str(source))
            token_data = json.dumps({
                "access_token": "new-token-from-kiro-cli",
                "refresh_token": "refresh-token-abc",
                "expires_at": "2099-01-01T00:00:00+00:00",
                "region": "us-east-1",
                "startUrl": "https://example.com",
                "provider": "test",
            })
            conn.execute("UPDATE auth_kv SET value = ? WHERE key = ?", (token_data, "kirocli:social:token"))
            conn.commit()
            conn.close()

            # Refresh the copy
            manager._refresh_sqlite_copy()

        assert manager._access_token == "new-token-from-kiro-cli"

    def test_write_back_goes_to_copy_not_original(self, tmp_path: Path) -> None:
        """_save_credentials_to_sqlite() writes to the copy, not the original."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source)
        original_hash = _file_hash(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            manager = KiroAuthManager(sqlite_db=str(source))

            # Simulate a token refresh updating in-memory state
            manager._access_token = "refreshed-token-xyz"
            manager._save_credentials_to_sqlite()

        # Original is untouched
        assert _file_hash(source) == original_hash

        # Copy has the updated token
        conn = sqlite3.connect(manager._sqlite_db)
        row = conn.execute("SELECT value FROM auth_kv WHERE key = 'kirocli:social:token'").fetchone()
        conn.close()
        data = json.loads(row[0])
        assert data["access_token"] == "refreshed-token-xyz"

    def test_original_db_never_modified(self, tmp_path: Path) -> None:
        """The original database file hash does not change after all operations."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source)
        original_hash = _file_hash(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            manager = KiroAuthManager(sqlite_db=str(source))

            # Load, refresh copy, write back
            manager._refresh_sqlite_copy()
            manager._access_token = "another-token"
            manager._save_credentials_to_sqlite()
            manager._refresh_sqlite_copy()

        assert _file_hash(source) == original_hash
