"""Unit tests for kiro/sqlite_copy.py."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro.sqlite_copy import (
    copy_sqlite_db,
    copy_if_missing,
    get_working_db_path,
    read_credentials_from_source,
    _get_copy_filename,
)


def _create_test_db(path: Path) -> None:
    """Create a minimal SQLite database for testing."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO auth_kv (key, value) VALUES ('test_key', 'test_value')")
    conn.commit()
    conn.close()


def _create_auth_db(
    path: Path,
    access_token: str = "tok-123",
    refresh_token: str = "ref-abc",
    expires_at: str = "2099-01-01T00:00:00+00:00",
    client_id: str = "",
    client_secret: str = "",
    include_state: bool = False,
    profile_arn_region: str = "us-east-1",
) -> None:
    """Create a SQLite database mimicking kiro-cli with auth_kv and state tables."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
    token_data = json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at,
        "region": "us-east-1",
        "scopes": ["codewhisperer:completions"],
    })
    conn.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("kirocli:social:token", token_data),
    )
    if client_id:
        reg_data = json.dumps({
            "client_id": client_id,
            "client_secret": client_secret,
            "region": "us-west-2",
        })
        conn.execute(
            "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
            ("kirocli:odic:device-registration", reg_data),
        )
    if include_state:
        conn.execute("CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT)")
        profile = json.dumps({
            "arn": f"arn:aws:codewhisperer:{profile_arn_region}:123456:profile/abc"
        })
        conn.execute(
            "INSERT INTO state (key, value) VALUES (?, ?)",
            ("api.codewhisperer.profile", profile),
        )
    conn.commit()
    conn.close()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestCopySqliteDb:
    """Tests for copy_sqlite_db function."""

    def test_creates_copy(self, tmp_path: Path) -> None:
        """Copy is created and contains the same data as the original."""
        source = tmp_path / "original" / "data.sqlite3"
        source.parent.mkdir()
        _create_test_db(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            result = copy_sqlite_db(str(source))

        assert Path(result).exists()
        conn = sqlite3.connect(result)
        row = conn.execute("SELECT value FROM auth_kv WHERE key = 'test_key'").fetchone()
        conn.close()
        assert row[0] == "test_value"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        """Second copy overwrites the first with fresh data from source."""
        source = tmp_path / "data.sqlite3"
        _create_test_db(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            copy_sqlite_db(str(source))

            # Modify source
            conn = sqlite3.connect(str(source))
            conn.execute("UPDATE auth_kv SET value = 'updated' WHERE key = 'test_key'")
            conn.commit()
            conn.close()

            # Re-copy
            result = copy_sqlite_db(str(source))

        conn = sqlite3.connect(result)
        row = conn.execute("SELECT value FROM auth_kv WHERE key = 'test_key'").fetchone()
        conn.close()
        assert row[0] == "updated"

    def test_source_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when source does not exist."""
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(tmp_path / "copies")):
            with pytest.raises(FileNotFoundError):
                copy_sqlite_db(str(tmp_path / "nonexistent.sqlite3"))

    def test_copy_dir_created_on_demand(self, tmp_path: Path) -> None:
        """The copy directory is created if it does not exist."""
        source = tmp_path / "data.sqlite3"
        _create_test_db(source)

        copy_dir = tmp_path / "deep" / "nested" / "copies"
        assert not copy_dir.exists()

        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            result = copy_sqlite_db(str(source))

        assert copy_dir.exists()
        assert Path(result).exists()

    def test_custom_copy_dir(self, tmp_path: Path) -> None:
        """Monkeypatching SQLITE_COPY_DIR overrides the default location."""
        source = tmp_path / "data.sqlite3"
        _create_test_db(source)

        custom_dir = tmp_path / "custom_location"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(custom_dir)):
            result = copy_sqlite_db(str(source))

        assert str(custom_dir) in result


class TestCopyIfMissing:
    """Tests for copy_if_missing function."""

    def test_creates_when_absent(self, tmp_path: Path) -> None:
        """Creates a copy when no working copy exists."""
        source = tmp_path / "data.sqlite3"
        _create_test_db(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            result = copy_if_missing(str(source))

        assert Path(result).exists()
        conn = sqlite3.connect(result)
        row = conn.execute("SELECT value FROM auth_kv WHERE key = 'test_key'").fetchone()
        conn.close()
        assert row[0] == "test_value"

    def test_skips_when_exists(self, tmp_path: Path) -> None:
        """Does not re-copy when working copy already exists."""
        source = tmp_path / "data.sqlite3"
        _create_test_db(source)

        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            first = copy_if_missing(str(source))
            mtime_before = Path(first).stat().st_mtime

            time.sleep(0.05)

            second = copy_if_missing(str(source))
            mtime_after = Path(second).stat().st_mtime

        assert first == second
        assert mtime_before == mtime_after

    def test_source_not_found_no_copy(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when source is missing and no copy exists."""
        copy_dir = tmp_path / "copies"
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(copy_dir)):
            with pytest.raises(FileNotFoundError):
                copy_if_missing(str(tmp_path / "nonexistent.sqlite3"))


class TestReadCredentialsFromSource:
    """Tests for read_credentials_from_source function."""

    TOKEN_KEYS = ["kirocli:social:token", "kirocli:odic:token"]
    REG_KEYS = ["kirocli:odic:device-registration"]

    def test_returns_token_fields(self, tmp_path: Path) -> None:
        """Reads access_token, refresh_token, expires_at, region, scopes."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source)

        creds = read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert creds["access_token"] == "tok-123"
        assert creds["refresh_token"] == "ref-abc"
        assert creds["region"] == "us-east-1"
        assert creds["scopes"] == ["codewhisperer:completions"]
        assert creds["expires_at"] is not None
        assert creds["sqlite_token_key"] == "kirocli:social:token"

    def test_returns_device_registration(self, tmp_path: Path) -> None:
        """Reads client_id and client_secret from device registration."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source, client_id="cid-1", client_secret="csec-2")

        creds = read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert creds["client_id"] == "cid-1"
        assert creds["client_secret"] == "csec-2"

    def test_returns_detected_api_region(self, tmp_path: Path) -> None:
        """Extracts API region from profile ARN in state table."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source, include_state=True, profile_arn_region="eu-central-1")

        creds = read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert creds["detected_api_region"] == "eu-central-1"

    def test_does_not_modify_source(self, tmp_path: Path) -> None:
        """Source database is not modified by read-only access."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source)
        hash_before = _file_hash(source)

        read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert _file_hash(source) == hash_before

    def test_source_not_found(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when source does not exist."""
        with pytest.raises(FileNotFoundError):
            read_credentials_from_source(
                str(tmp_path / "missing.sqlite3"), self.TOKEN_KEYS, self.REG_KEYS
            )

    def test_no_matching_keys(self, tmp_path: Path) -> None:
        """Returns empty dict when no matching keys are found."""
        source = tmp_path / "data.sqlite3"
        conn = sqlite3.connect(str(source))
        conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
            ("unrelated:key", '{"foo": "bar"}'),
        )
        conn.commit()
        conn.close()

        creds = read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert creds == {}

    def test_fallback_to_second_token_key(self, tmp_path: Path) -> None:
        """Falls back to second token key when first is absent."""
        source = tmp_path / "data.sqlite3"
        conn = sqlite3.connect(str(source))
        conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
        token_data = json.dumps({
            "access_token": "fallback-tok",
            "refresh_token": "fallback-ref",
        })
        conn.execute(
            "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
            ("kirocli:odic:token", token_data),
        )
        conn.commit()
        conn.close()

        creds = read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert creds["access_token"] == "fallback-tok"
        assert creds["sqlite_token_key"] == "kirocli:odic:token"

    def test_nanosecond_expires_at(self, tmp_path: Path) -> None:
        """Handles kiro-cli nanosecond precision in expires_at."""
        source = tmp_path / "data.sqlite3"
        _create_auth_db(source, expires_at="2099-06-15T12:30:45.123456789+00:00")

        creds = read_credentials_from_source(str(source), self.TOKEN_KEYS, self.REG_KEYS)

        assert creds["expires_at"] is not None
        assert creds["expires_at"].microsecond == 123456


class TestGetWorkingDbPath:
    """Tests for get_working_db_path function."""

    def test_deterministic(self, tmp_path: Path) -> None:
        """Same source path always produces the same working path."""
        source = str(tmp_path / "data.sqlite3")
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(tmp_path / "copies")):
            path1 = get_working_db_path(source)
            path2 = get_working_db_path(source)

        assert path1 == path2

    def test_different_sources(self, tmp_path: Path) -> None:
        """Different source paths produce different working paths."""
        with patch("kiro.sqlite_copy.SQLITE_COPY_DIR", str(tmp_path / "copies")):
            path1 = get_working_db_path(str(tmp_path / "db1.sqlite3"))
            path2 = get_working_db_path(str(tmp_path / "db2.sqlite3"))

        assert path1 != path2


class TestGetCopyFilename:
    """Tests for _get_copy_filename helper."""

    def test_format(self, tmp_path: Path) -> None:
        """Filename follows the expected format."""
        filename = _get_copy_filename(str(tmp_path / "data.sqlite3"))
        assert filename.startswith("kiro-db-")
        assert filename.endswith(".sqlite3")
        # hash portion is 16 chars
        hash_part = filename[len("kiro-db-"):-len(".sqlite3")]
        assert len(hash_part) == 16
