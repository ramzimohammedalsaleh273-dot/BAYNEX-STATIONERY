import sqlite3
from contextlib import closing

import pytest

from baynex_stationery.services.database_backup import create_backup, restore_backup


def make_database(path, value):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS records (value TEXT NOT NULL)")
        connection.execute("DELETE FROM records")
        connection.execute("INSERT INTO records(value) VALUES (?)", (value,))
        connection.commit()


def read_value(path):
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT value FROM records").fetchone()[0]


def test_backup_and_restore_preserve_a_consistent_database(tmp_path):
    database = tmp_path / "application.sqlite3"
    backup = tmp_path / "backups" / "before-change.sqlite3"
    make_database(database, "original")

    assert create_backup(database, backup) == backup
    make_database(database, "changed")
    restore_backup(backup, database)

    assert read_value(database) == "original"
    assert read_value(backup) == "original"


def test_backup_rejects_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_backup(tmp_path / "missing.sqlite3", tmp_path / "backup.sqlite3")


def test_backup_rejects_same_source_and_destination(tmp_path):
    database = tmp_path / "application.sqlite3"
    make_database(database, "original")
    with pytest.raises(ValueError, match="مختلفاً"):
        create_backup(database, database)


def test_restore_rejects_corrupt_backup_without_overwriting_database(tmp_path):
    database = tmp_path / "application.sqlite3"
    corrupt = tmp_path / "corrupt.sqlite3"
    make_database(database, "keep-me")
    corrupt.write_bytes(b"not a SQLite database")

    with pytest.raises(sqlite3.DatabaseError):
        restore_backup(corrupt, database)

    assert read_value(database) == "keep-me"
