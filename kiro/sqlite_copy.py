"""
SQLite database copy manager.

Copies the kiro-cli SQLite database to a working location so the gateway
and kiro-cli don't compete for locks on the same file.
"""

import hashlib
import shutil
from pathlib import Path

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
