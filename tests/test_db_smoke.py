"""Smoke test: schema can be applied to a real on-disk SQLite file (not just :memory:)."""

import sqlite3
from pathlib import Path


def test_schema_applies_to_disk_db(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parent.parent
    schema_sql = (repo_root / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    db_path = tmp_path / "pechepro.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_sql)
    conn.commit()
    # Insert + read smoke
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (1, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.commit()
    row = conn.execute("SELECT common_name_fr FROM species WHERE id=1").fetchone()
    assert row[0] == "Doré jaune"
    conn.close()
    assert db_path.stat().st_size > 0
