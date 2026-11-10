"""Atomic SQLite backup and restore helpers.

The caller must close application sessions before restoring over an active database.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path


def _open_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"ملف قاعدة البيانات غير موجود: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _assert_integrity(connection: sqlite3.Connection) -> None:
    result = connection.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise ValueError(f"فشل فحص سلامة قاعدة البيانات: {result}")


def _copy_database_atomically(source: Path, destination: Path) -> Path:
    source = Path(source)
    destination = Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError("يجب أن يكون مسار النسخة الاحتياطية مختلفاً عن قاعدة البيانات الأصلية")

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".sqlite-tmp",
        dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with _open_read_only(source) as source_connection:
            with sqlite3.connect(temporary) as destination_connection:
                source_connection.backup(destination_connection)
                _assert_integrity(destination_connection)
        os.replace(temporary, destination)
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def create_backup(database_path: str | Path, backup_path: str | Path) -> Path:
    """Create a consistent SQLite snapshot, including committed WAL contents."""
    return _copy_database_atomically(Path(database_path), Path(backup_path))


def restore_backup(backup_path: str | Path, database_path: str | Path) -> Path:
    """Restore a validated backup atomically; close active app connections first."""
    return _copy_database_atomically(Path(backup_path), Path(database_path))
