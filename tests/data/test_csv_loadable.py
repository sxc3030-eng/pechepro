"""Round-trip test: every curated CSV must INSERT cleanly into the schema."""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

CURATED = Path(__file__).resolve().parents[2] / "data" / "curated"


def _rows(name: str) -> list[dict[str, str]]:
    with (CURATED / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _insert(conn: sqlite3.Connection, table: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(cols))
    col_list = ", ".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    for r in rows:
        # Empty strings → None for nullable numeric/foreign-key fields
        values = []
        for c in cols:
            v = r[c]
            if v == "":
                values.append(None)
            else:
                values.append(v)
        conn.execute(sql, values)


def test_full_seed_loads_into_empty_db(empty_db: sqlite3.Connection) -> None:
    """Load every CSV into the empty DB in FK-safe order; counts match files."""
    order = [
        ("species", "species.csv"),
        ("regions", "regions.csv"),
        ("water_types", "water_types.csv"),
        ("lures", "lures.csv"),
        ("color_visibility", "color_visibility.csv"),
        ("solunar_rules", "solunar_rules.csv"),
        ("baro_rules", "baro_rules.csv"),
        ("tips", "tips.csv"),  # depends on species, regions, water_types
    ]
    for table, fname in order:
        rows = _rows(fname)
        _insert(empty_db, table, rows)
        empty_db.commit()
        got = empty_db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert got == len(rows), f"{table}: expected {len(rows)} rows, got {got}"


def test_tips_fk_to_species_enforced(empty_db: sqlite3.Connection) -> None:
    """Loading tips.csv must succeed only if every species_id resolves."""
    _insert(empty_db, "species", _rows("species.csv"))
    _insert(empty_db, "regions", _rows("regions.csv"))
    _insert(empty_db, "water_types", _rows("water_types.csv"))
    empty_db.commit()
    # Should not raise IntegrityError
    _insert(empty_db, "tips", _rows("tips.csv"))
    empty_db.commit()
