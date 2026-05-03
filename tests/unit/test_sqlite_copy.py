"""Unit tests for kiro/sqlite_copy.py."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro.sqlite_copy import copy_sqlite_db, get_working_db_path, _get_copy_filename


def _create_test_db(path: Path) -> None:
    """Create a minimal SQLite database for testing."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO auth_kv (key, value) VALUES ('test_key', 'test_value')")
    conn.commit()
    conn.close()


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
