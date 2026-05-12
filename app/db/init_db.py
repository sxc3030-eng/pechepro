"""First-run database initialization for pechepro.

Applies schema.sql to a SQLite file at the platform-appropriate location.
Optionally loads seed CSVs from data/curated/ if present.
Detects and recovers from corrupt DB files.
"""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "app" / "db" / "schema.sql"


# Map CSV filename -> (table_name, column_list_excluding_created_at).
SEED_TABLES: dict[str, tuple[str, list[str]]] = {
    "species.csv": (
        "species",
        [
            "id",
            "common_name_fr",
            "common_name_en",
            "scientific_name",
            "family",
            "typical_habitat",
            "image_url",
        ],
    ),
    "regions.csv": (
        "regions",
        [
            "id",
            "name_fr",
            "name_en",
            "country",
            "iso_code",
            "bbox_lat_min",
            "bbox_lat_max",
            "bbox_lon_min",
            "bbox_lon_max",
        ],
    ),
    "water_types.csv": (
        "water_types",
        ["id", "name_fr", "name_en"],
    ),
    "lures.csv": (
        "lures",
        ["id", "name_fr", "name_en", "category", "image_url"],
    ),
    "color_visibility.csv": (
        "color_visibility",
        [
            "id",
            "water_clarity",
            "light_level",
            "color",
            "visibility_score",
            "notes_fr",
            "notes_en",
        ],
    ),
    "tips.csv": (
        "tips",
        [
            "id",
            "species_id",
            "region_id",
            "water_type_id",
            "season",
            "baro_trend",
            "moon_phase",
            "temp_water_min_c",
            "temp_water_max_c",
            "time_of_day",
            "tip_text_fr",
            "tip_text_en",
            "source_url",
            "confidence",
        ],
    ),
    "solunar_rules.csv": (
        "solunar_rules",
        ["id", "period_type", "duration_minutes", "weight"],
    ),
    "baro_rules.csv": (
        "baro_rules",
        ["id", "species_id", "baro_trend", "activity_score", "notes_fr", "notes_en"],
    ),
}


def default_db_path() -> Path:
    """Return the platform-appropriate DB path.

    Windows: %LOCALAPPDATA%\\pechepro\\pechepro.db
    Other (tests/CI): repo_root/.local/pechepro.db
    """
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "pechepro" / "pechepro.db"
    return REPO_ROOT / ".local" / "pechepro.db"


def apply_schema(db_path: Path) -> None:
    """Apply schema.sql to the SQLite file at db_path. Idempotent."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def ensure_database(db_path: Path) -> bool:
    """Ensure the database exists with schema applied.

    Returns True if this was the first run (DB had to be created),
    False if the DB was already present and valid.
    """
    is_first_run = not db_path.exists()
    apply_schema(db_path)
    return is_first_run


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f"SELECT count(*) FROM {table}")  # noqa: S608 (table from SEED_TABLES)
    return int(cur.fetchone()[0])


def _normalize_value(raw: str) -> str | None:
    """Empty strings in CSVs become SQL NULL."""
    return None if raw == "" else raw


def _insert_csv(conn: sqlite3.Connection, csv_path: Path, table: str, cols: list[str]) -> int:
    placeholders = ",".join("?" for _ in cols)
    col_list = ",".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"  # noqa: S608 (table from SEED_TABLES)
    inserted = 0
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = [_normalize_value(row.get(c, "") or "") for c in cols]
            conn.execute(sql, values)
            inserted += 1
    return inserted


def load_seed_csvs(db_path: Path, csv_dir: Path) -> dict[str, int]:
    """Load curated CSVs from csv_dir into the database at db_path.

    For each curated table:
    - If csv_dir doesn't exist, return {} (silent).
    - If the CSV file is missing, skip silently.
    - If the table is already non-empty, record 0 inserted.
    - Otherwise, read CSV with header, INSERT rows, return inserted count.

    Empty strings in CSV become NULL.
    """
    counts: dict[str, int] = {}
    if not csv_dir.exists():
        return counts
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        for filename, (table, cols) in SEED_TABLES.items():
            csv_path = csv_dir / filename
            if not csv_path.exists():
                continue
            if _row_count(conn, table) > 0:
                counts[table] = 0
                continue
            inserted = _insert_csv(conn, csv_path, table, cols)
            counts[table] = inserted
        conn.commit()
    finally:
        conn.close()
    return counts


def is_db_corrupt(db_path: Path) -> bool:
    """Return True if db_path exists but cannot be opened as a valid SQLite database.

    Missing file returns False (caller treats absence as 'first run', not corruption).
    """
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(db_path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            return result is None or result[0] != "ok"
        finally:
            conn.close()
    except sqlite3.DatabaseError:
        return True


def recover_corrupt_db(db_path: Path) -> None:
    """Replace a corrupt database file with a freshly initialized one.

    Caller has decided the DB is corrupt; this function unlinks it,
    re-applies the schema, and returns. Callers may then reload seed
    data via load_seed_csvs.
    """
    if db_path.exists():
        db_path.unlink()
    apply_schema(db_path)
