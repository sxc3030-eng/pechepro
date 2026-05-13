"""Shared pytest fixtures."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "app" / "db" / "schema.sql"


@pytest.fixture
def empty_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide a connection to a fresh SQLite database with schema applied."""
    db_path = tmp_path / "pechepro_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    yield conn
    conn.close()
