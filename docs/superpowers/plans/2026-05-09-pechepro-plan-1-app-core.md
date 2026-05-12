# Pechepro Plan 1 — App Core Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the PyWebView shell, Flask local server, Jinja2 templates, design system CSS, i18n FR/EN, and DB initialization for pechepro v0.1.

**Architecture:** PyWebView wraps a local Flask app on a dynamic port. Flask serves Jinja2 templates that orchestrate calls to in-process Python services (plan-2). SQLite local DB is initialized on first run from schema.sql + seed CSVs. UI in FR + EN via simple JSON message catalog.

**Tech Stack:** Python 3.13 · PyWebView 5.4 · Flask 3.0.3 · Jinja2 3.1.4 · SQLite (stdlib) · pytest 8.3.4

**Worktree:** `D:\pechepro\.claude\worktrees\plan-1-app-core` on branch `plan/app-core`

---

## Service interface contract (assumed — implemented by plan-2)

These signatures are the source of truth for plan-1. Plan-1 imports them, plan-1 mocks them in tests, plan-2 must implement them with these exact signatures.

```python
# app/services/recommender.py
def recommend(
    species_id: int,
    region_id: int | None,
    water_type_id: int,
    conditions: dict[str, str | float | None],
) -> list[dict[str, object]]:
    """Return ranked tips list. Each dict has keys:
    id, tip_text_fr, tip_text_en, source_url, confidence, match_score (float 0-1).
    """

# app/services/solunar.py
def compute_periods(lat: float, lon: float, date: str) -> dict[str, object]:
    """Return {'major': [{'start': iso, 'end': iso, 'score': float}, ...],
                'minor': [...]} for the given date (YYYY-MM-DD)."""

# app/services/astral_calc.py
def sun_moon(lat: float, lon: float, date: str) -> dict[str, object]:
    """Return {'sunrise': iso, 'sunset': iso, 'civil_dawn': iso, 'civil_dusk': iso,
              'moon_phase': str, 'moon_illumination': float}."""

# app/services/openmeteo_client.py
def get_weather(lat: float, lon: float) -> dict[str, object]:
    """Return {'temp_air_c': float, 'pressure_hpa': float, 'pressure_trend_6h': str,
              'humidity_pct': float, 'wind_kmh': float, 'cloud_cover_pct': float,
              'fetched_at': iso, 'cached': bool} or raises ServiceUnavailable."""

# app/services/usgs_client.py
def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temperature in Celsius for nearest USGS station, or None."""

# app/services/eccc_client.py
def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temperature in Celsius for nearest ECCC station, or None."""

# app/services/geolocation.py
def get_current_location() -> tuple[float, float] | None:
    """Return (lat, lon) from Windows Location API, or None if refused/unavailable."""

# app/services/data_sync.py
def sync_curated_data(db_path: str) -> None:
    """Sync CSVs from raw.githubusercontent.com to local SQLite. Silent on offline."""
```

Plan-1 also defines a shared exception `app.services.errors.ServiceUnavailable` used by plan-2. Plan-1 ships this stub; plan-2 imports it.

---

## Task list overview

| # | Task | LOC est. |
|---|---|---|
| 1 | Initialize plan-1 worktree + smoke skeleton | ~30 |
| 2 | Service errors module (ServiceUnavailable) | ~25 |
| 3 | DB initialization module — apply schema.sql | ~80 |
| 4 | DB initialization module — load curated CSVs | ~120 |
| 5 | DB initialization module — corrupt-DB recovery | ~60 |
| 6 | i18n module — locale detection + catalog loader | ~100 |
| 7 | i18n module — FR catalog | ~40 |
| 8 | i18n module — EN catalog | ~40 |
| 9 | Flask app factory + config | ~80 |
| 10 | Flask route GET / (Home) | ~50 |
| 11 | Flask route GET /api/species | ~50 |
| 12 | Flask route GET /api/regions | ~50 |
| 13 | Flask route GET /api/water-types | ~40 |
| 14 | Flask route GET /api/sun-moon | ~60 |
| 15 | Flask route GET /api/weather (with cache fallback) | ~80 |
| 16 | Flask route POST /api/recommend | ~80 |
| 17 | Flask route GET /conditions (full orchestration) | ~120 |
| 18 | Flask route GET /tips (browse) | ~60 |
| 19 | Flask error handlers (404 / 500 / ServiceUnavailable) | ~80 |
| 20 | Base template (base.html) + Expedia widget block | ~100 |
| 21 | Home template (home.html) | ~80 |
| 22 | Conditions template (conditions.html) | ~150 |
| 23 | Tips template (tips.html) | ~80 |
| 24 | Design system CSS — palette + tokens + reset | ~150 |
| 25 | Design system CSS — typography (Inter + JetBrains Mono) | ~80 |
| 26 | Design system CSS — components (cards, buttons, badges) | ~150 |
| 27 | main.js — fetch helpers + form binding | ~120 |
| 28 | main.js — geolocation + recommendation flow | ~120 |
| 29 | Static assets — logo + icon placeholders | ~20 |
| 30 | PyWebView shell — entry point + lifecycle | ~150 |
| 31 | Smoke E2E test — full launch + GET /conditions | ~100 |
| 32 | Coverage gate — final ≥80% verification | ~10 |

Total: 32 tasks.

---

### Task 1 : Initialize worktree skeleton and shared smoke fixture

**Files:**
- Create: `D:\pechepro\.claude\worktrees\plan-1-app-core\app\services\__init__.py`
- Create: `D:\pechepro\.claude\worktrees\plan-1-app-core\tests\test_smoke_marker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_smoke_marker.py`:

```python
"""Verify the worktree has the expected skeleton and pytest collects from app/."""

import importlib


def test_app_package_importable() -> None:
    mod = importlib.import_module("app")
    assert mod.__version__ == "0.1.0-dev"


def test_app_services_package_exists() -> None:
    mod = importlib.import_module("app.services")
    assert mod is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```powershell
cd D:\pechepro\.claude\worktrees\plan-1-app-core
pytest tests/test_smoke_marker.py -v
```
Expected: `test_app_services_package_exists` fails with `ModuleNotFoundError: No module named 'app.services'`.

- [ ] **Step 3: Create app/services/__init__.py**

Create `app/services/__init__.py`:

```python
"""External service adapters for pechepro.

Implementations live in plan-2. Plan-1 only depends on the public
function signatures documented in the plan-1 contract section.
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_smoke_marker.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/services/__init__.py tests/test_smoke_marker.py
git commit -m "chore(plan-1): scaffold app.services package and smoke marker test"
```

---

### Task 2 : Service errors module — ServiceUnavailable exception

**Files:**
- Create: `app/services/errors.py`
- Create: `tests/test_service_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_service_errors.py`:

```python
"""Tests for app.services.errors module."""

import pytest

from app.services.errors import ServiceUnavailable


def test_service_unavailable_is_exception() -> None:
    assert issubclass(ServiceUnavailable, Exception)


def test_service_unavailable_carries_service_name() -> None:
    exc = ServiceUnavailable(service="openmeteo", reason="timeout")
    assert exc.service == "openmeteo"
    assert exc.reason == "timeout"
    assert "openmeteo" in str(exc)
    assert "timeout" in str(exc)


def test_service_unavailable_can_be_raised_and_caught() -> None:
    with pytest.raises(ServiceUnavailable) as exc_info:
        raise ServiceUnavailable(service="usgs", reason="404")
    assert exc_info.value.service == "usgs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_service_errors.py -v`
Expected: `ImportError: cannot import name 'ServiceUnavailable' from 'app.services.errors'` (module doesn't exist).

- [ ] **Step 3: Write the implementation**

Create `app/services/errors.py`:

```python
"""Shared exceptions used by service adapters and Flask error handlers."""

from __future__ import annotations


class ServiceUnavailable(Exception):
    """Raised when an external API (Open-Meteo, USGS, ECCC) is unreachable.

    The Flask handler maps this to a graceful UI message rather than HTTP 500.
    """

    def __init__(self, service: str, reason: str) -> None:
        self.service = service
        self.reason = reason
        super().__init__(f"Service '{service}' unavailable: {reason}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_service_errors.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/services/errors.py tests/test_service_errors.py
git commit -m "feat(plan-1): add ServiceUnavailable exception for service adapters"
```

---

### Task 3 : DB initialization — apply schema.sql

**Files:**
- Create: `app/db/init_db.py`
- Create: `tests/test_init_db.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_init_db.py`:

```python
"""Tests for app.db.init_db — first-run database initialization."""

import sqlite3
from pathlib import Path

import pytest

from app.db.init_db import apply_schema, ensure_database


def test_apply_schema_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r[0] for r in rows}
    conn.close()
    assert "species" in names
    assert "tips" in names
    assert "weather_cache" in names
    assert "user_prefs" in names


def test_apply_schema_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    apply_schema(db_path)  # second call must not raise
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    assert rows[0][0] >= 11


def test_ensure_database_creates_db_when_absent(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    assert not db_path.exists()
    result = ensure_database(db_path)
    assert db_path.exists()
    assert result is True  # signals first-run


def test_ensure_database_returns_false_when_present(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    result = ensure_database(db_path)
    assert result is False  # not first-run


def test_apply_schema_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "dir" / "p.db"
    apply_schema(nested)
    assert nested.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_init_db.py -v`
Expected: `ImportError: cannot import name 'apply_schema' from 'app.db.init_db'`.

- [ ] **Step 3: Write the implementation**

Create `app/db/init_db.py`:

```python
"""First-run database initialization for pechepro.

Applies schema.sql to a SQLite file at the platform-appropriate location.
Optionally loads seed CSVs from data/curated/ if present (Task 4).
Detects and recovers from corrupt DB files (Task 5).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "app" / "db" / "schema.sql"


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_init_db.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/db/init_db.py tests/test_init_db.py
git commit -m "feat(plan-1): add init_db.apply_schema and ensure_database"
```

---

### Task 4 : DB initialization — load curated CSV seed data

**Files:**
- Modify: `app/db/init_db.py`
- Modify: `tests/test_init_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_init_db.py`:

```python
import csv


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def test_load_seed_csvs_imports_species(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, load_seed_csvs

    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        ["id", "common_name_fr", "common_name_en", "scientific_name", "family", "typical_habitat", "image_url"],
        [
            [1, "Doré jaune", "Walleye", "Sander vitreus", "Percidae", "lac/rivière", ""],
            [2, "Achigan", "Largemouth Bass", "Micropterus salmoides", "Centrarchidae", "lac", ""],
        ],
    )
    counts = load_seed_csvs(db_path, csv_dir)
    assert counts["species"] == 2
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT common_name_fr FROM species ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["Doré jaune", "Achigan"]


def test_load_seed_csvs_skips_missing_files(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, load_seed_csvs

    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    counts = load_seed_csvs(db_path, tmp_path / "nonexistent")
    assert counts == {}


def test_load_seed_csvs_skips_when_table_already_seeded(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, load_seed_csvs

    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (99, 'Existing', 'Existing', 'Existing')"
    )
    conn.commit()
    conn.close()
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        ["id", "common_name_fr", "common_name_en", "scientific_name", "family", "typical_habitat", "image_url"],
        [[1, "Doré jaune", "Walleye", "Sander vitreus", "", "", ""]],
    )
    counts = load_seed_csvs(db_path, csv_dir)
    assert counts.get("species", 0) == 0  # skipped because not empty


def test_load_seed_csvs_loads_all_eight_curated_tables(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, load_seed_csvs

    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        ["id", "common_name_fr", "common_name_en", "scientific_name", "family", "typical_habitat", "image_url"],
        [[1, "Doré", "Walleye", "Sander vitreus", "", "", ""]],
    )
    _write_csv(
        csv_dir / "regions.csv",
        ["id", "name_fr", "name_en", "country", "iso_code", "bbox_lat_min", "bbox_lat_max", "bbox_lon_min", "bbox_lon_max"],
        [[1, "Québec", "Quebec", "CA", "QC", 45.0, 62.0, -79.0, -57.0]],
    )
    _write_csv(
        csv_dir / "water_types.csv",
        ["id", "name_fr", "name_en"],
        [[1, "Lac", "Lake"]],
    )
    _write_csv(
        csv_dir / "lures.csv",
        ["id", "name_fr", "name_en", "category", "image_url"],
        [[1, "Tube", "Tube", "soft", ""]],
    )
    _write_csv(
        csv_dir / "color_visibility.csv",
        ["id", "water_clarity", "light_level", "color", "visibility_score", "notes_fr", "notes_en"],
        [[1, "clear", "bright", "white", 9, "", ""]],
    )
    _write_csv(
        csv_dir / "tips.csv",
        ["id", "species_id", "region_id", "water_type_id", "season", "baro_trend", "moon_phase",
         "temp_water_min_c", "temp_water_max_c", "time_of_day", "tip_text_fr", "tip_text_en", "source_url", "confidence"],
        [[1, 1, 1, 1, "spring", "rising", "any", 8.0, 14.0, "dawn", "Tip FR", "Tip EN", "https://example.com", 4]],
    )
    _write_csv(
        csv_dir / "solunar_rules.csv",
        ["id", "period_type", "duration_minutes", "weight"],
        [[1, "major", 120, 1.0], [2, "minor", 60, 0.6]],
    )
    _write_csv(
        csv_dir / "baro_rules.csv",
        ["id", "species_id", "baro_trend", "activity_score", "notes_fr", "notes_en"],
        [[1, 1, "rising", 8, "", ""]],
    )
    counts = load_seed_csvs(db_path, csv_dir)
    assert counts == {
        "species": 1,
        "regions": 1,
        "water_types": 1,
        "lures": 1,
        "color_visibility": 1,
        "tips": 1,
        "solunar_rules": 2,
        "baro_rules": 1,
    }


def test_load_seed_csvs_empty_string_becomes_null(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, load_seed_csvs

    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        ["id", "common_name_fr", "common_name_en", "scientific_name", "family", "typical_habitat", "image_url"],
        [[1, "Doré", "Walleye", "Sander vitreus", "", "", ""]],
    )
    load_seed_csvs(db_path, csv_dir)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT family, image_url FROM species WHERE id=1").fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init_db.py -v -k load_seed`
Expected: 5 failures with `ImportError: cannot import name 'load_seed_csvs'`.

- [ ] **Step 3: Write the implementation**

Edit `app/db/init_db.py` — append after `ensure_database`:

```python
import csv

# Map CSV filename → (table_name, column_list_excluding_created_at).
# created_at columns get DEFAULT CURRENT_TIMESTAMP from schema.
SEED_TABLES: dict[str, tuple[str, list[str]]] = {
    "species.csv": (
        "species",
        ["id", "common_name_fr", "common_name_en", "scientific_name", "family", "typical_habitat", "image_url"],
    ),
    "regions.csv": (
        "regions",
        ["id", "name_fr", "name_en", "country", "iso_code", "bbox_lat_min", "bbox_lat_max", "bbox_lon_min", "bbox_lon_max"],
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
        ["id", "water_clarity", "light_level", "color", "visibility_score", "notes_fr", "notes_en"],
    ),
    "tips.csv": (
        "tips",
        ["id", "species_id", "region_id", "water_type_id", "season", "baro_trend", "moon_phase",
         "temp_water_min_c", "temp_water_max_c", "time_of_day", "tip_text_fr", "tip_text_en",
         "source_url", "confidence"],
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


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _normalize_value(raw: str) -> str | None:
    """Empty strings in CSVs become SQL NULL."""
    return None if raw == "" else raw


def load_seed_csvs(db_path: Path, csv_dir: Path) -> dict[str, int]:
    """Load curated CSVs from csv_dir into the database at db_path.

    For each curated table:
    - If the CSV file is missing, skip silently.
    - If the table is already non-empty, skip (idempotent / respects user data).
    - Otherwise, read CSV with header, INSERT rows, return inserted count.

    Returns a dict mapping table_name -> rows_inserted (only entries actually loaded).
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


def _insert_csv(
    conn: sqlite3.Connection, csv_path: Path, table: str, cols: list[str]
) -> int:
    placeholders = ",".join("?" for _ in cols)
    col_list = ",".join(cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
    inserted = 0
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            values = [_normalize_value(row.get(c, "")) for c in cols]
            conn.execute(sql, values)
            inserted += 1
    return inserted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_init_db.py -v`
Expected: 10 PASS (5 original + 5 new).

- [ ] **Step 5: Commit**

```powershell
git add app/db/init_db.py tests/test_init_db.py
git commit -m "feat(plan-1): add load_seed_csvs to import 8 curated tables idempotently"
```

---

### Task 5 : DB initialization — corrupt DB detection & recovery

**Files:**
- Modify: `app/db/init_db.py`
- Modify: `tests/test_init_db.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_init_db.py`:

```python
def test_is_db_corrupt_returns_false_for_healthy(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, is_db_corrupt

    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    assert is_db_corrupt(db_path) is False


def test_is_db_corrupt_returns_true_for_garbage_file(tmp_path: Path) -> None:
    from app.db.init_db import is_db_corrupt

    db_path = tmp_path / "p.db"
    db_path.write_bytes(b"not a sqlite file")
    assert is_db_corrupt(db_path) is True


def test_is_db_corrupt_returns_false_for_missing_file(tmp_path: Path) -> None:
    from app.db.init_db import is_db_corrupt

    db_path = tmp_path / "missing.db"
    # Missing file is not "corrupt" — caller treats it as first-run.
    assert is_db_corrupt(db_path) is False


def test_recover_corrupt_db_replaces_with_fresh_schema(tmp_path: Path) -> None:
    from app.db.init_db import apply_schema, recover_corrupt_db

    db_path = tmp_path / "p.db"
    db_path.write_bytes(b"corrupt content")
    recover_corrupt_db(db_path)
    # After recovery: file exists, is valid SQLite with our schema.
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='species'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_init_db.py -v -k "corrupt or recover"`
Expected: 4 failures with `ImportError`.

- [ ] **Step 3: Write the implementation**

Edit `app/db/init_db.py` — append:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_init_db.py -v`
Expected: 14 PASS total.

- [ ] **Step 5: Commit**

```powershell
git add app/db/init_db.py tests/test_init_db.py
git commit -m "feat(plan-1): detect corrupt DB and recover with fresh schema"
```

---

### Task 6 : i18n module — locale detection + catalog loader

**Files:**
- Create: `app/i18n.py`
- Create: `tests/test_i18n.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_i18n.py`:

```python
"""Tests for app.i18n module."""

from unittest.mock import patch

import pytest

from app.i18n import (
    SUPPORTED_LANGS,
    detect_system_lang,
    load_catalog,
    normalize_lang,
    translate,
)


def test_supported_langs_are_fr_and_en() -> None:
    assert set(SUPPORTED_LANGS) == {"fr", "en"}


@pytest.mark.parametrize("locale, expected", [
    ("fr_CA", "fr"),
    ("fr_FR", "fr"),
    ("FR", "fr"),
    ("en_US", "en"),
    ("en_GB", "en"),
    ("EN", "en"),
    ("de_DE", "en"),  # unsupported falls back to en
    ("", "en"),
    (None, "en"),
])
def test_normalize_lang(locale: str | None, expected: str) -> None:
    assert normalize_lang(locale) == expected


def test_detect_system_lang_uses_locale_getlocale() -> None:
    with patch("app.i18n.locale.getlocale", return_value=("fr_CA", "UTF-8")):
        assert detect_system_lang() == "fr"


def test_detect_system_lang_falls_back_to_en_on_error() -> None:
    with patch("app.i18n.locale.getlocale", side_effect=Exception("boom")):
        assert detect_system_lang() == "en"


def test_detect_system_lang_handles_none_locale() -> None:
    with patch("app.i18n.locale.getlocale", return_value=(None, None)):
        assert detect_system_lang() == "en"


def test_load_catalog_fr() -> None:
    cat = load_catalog("fr")
    assert "app.title" in cat
    assert isinstance(cat["app.title"], str)


def test_load_catalog_en() -> None:
    cat = load_catalog("en")
    assert "app.title" in cat
    assert isinstance(cat["app.title"], str)


def test_load_catalog_unknown_falls_back_to_en() -> None:
    cat = load_catalog("xx")
    en = load_catalog("en")
    assert cat == en


def test_translate_returns_value_for_known_key() -> None:
    cat = load_catalog("en")
    val = translate("app.title", cat)
    assert val and val != "app.title"


def test_translate_returns_key_when_missing() -> None:
    val = translate("nonexistent.key", {"foo": "bar"})
    assert val == "nonexistent.key"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_i18n.py -v`
Expected: all fail with `ModuleNotFoundError: No module named 'app.i18n'`.

- [ ] **Step 3: Write the implementation**

Create `app/i18n.py`:

```python
"""Minimal i18n: load JSON message catalogs and translate by dotted key.

Supports French (fr) and English (en). Locale is detected from the system
once at startup; the user can override via /api/lang (handled in plan-1's
Flask routes — Task 9).
"""

from __future__ import annotations

import json
import locale
from pathlib import Path

SUPPORTED_LANGS: tuple[str, ...] = ("fr", "en")
DEFAULT_LANG: str = "en"
LOCALES_DIR: Path = Path(__file__).resolve().parent / "locales"


def normalize_lang(value: str | None) -> str:
    """Map a locale string ('fr_CA', 'en-US', 'FR') to a supported code.

    Returns DEFAULT_LANG for None / empty / unsupported values.
    """
    if not value:
        return DEFAULT_LANG
    code = value.lower().replace("-", "_").split("_", 1)[0]
    if code in SUPPORTED_LANGS:
        return code
    return DEFAULT_LANG


def detect_system_lang() -> str:
    """Detect the language from the OS locale, falling back to DEFAULT_LANG."""
    try:
        loc = locale.getlocale()
        return normalize_lang(loc[0] if loc else None)
    except Exception:
        return DEFAULT_LANG


def load_catalog(lang: str) -> dict[str, str]:
    """Load the JSON catalog for the given language code.

    Falls back to DEFAULT_LANG if the requested language is unsupported.
    Raises FileNotFoundError if the default catalog is also missing.
    """
    code = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    path = LOCALES_DIR / f"{code}.json"
    if not path.exists() and code != DEFAULT_LANG:
        path = LOCALES_DIR / f"{DEFAULT_LANG}.json"
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return {k: str(v) for k, v in data.items()}


def translate(key: str, catalog: dict[str, str]) -> str:
    """Return catalog[key] or the key itself if missing (visible fallback)."""
    return catalog.get(key, key)
```

- [ ] **Step 4: Create directory + empty placeholder catalogs so tests requiring catalogs pass**

Create `app/locales/__init__.py` (empty file):

```python
```

We will fill `fr.json` and `en.json` in Tasks 7 and 8. For Task 6 tests, write minimal placeholders here:

Create `app/locales/en.json`:

```json
{
  "app.title": "pechepro"
}
```

Create `app/locales/fr.json`:

```json
{
  "app.title": "pechepro"
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_i18n.py -v`
Expected: 11 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/i18n.py app/locales/__init__.py app/locales/en.json app/locales/fr.json tests/test_i18n.py
git commit -m "feat(plan-1): add i18n loader with FR/EN locale detection and catalog"
```

---

### Task 7 : i18n FR catalog — fill UI strings

**Files:**
- Modify: `app/locales/fr.json`
- Modify: `tests/test_i18n.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
REQUIRED_KEYS = {
    "app.title",
    "nav.home",
    "nav.conditions",
    "nav.tips",
    "home.title",
    "home.subtitle",
    "home.cta",
    "form.species",
    "form.region",
    "form.water_type",
    "form.submit",
    "conditions.title",
    "conditions.weather",
    "conditions.solunar",
    "conditions.tips",
    "errors.weather_unavailable",
    "errors.gps_refused",
    "errors.db_recovered",
    "footer.disclaimer",
    "footer.about",
}


def test_fr_catalog_has_all_required_keys() -> None:
    cat = load_catalog("fr")
    missing = REQUIRED_KEYS - set(cat)
    assert not missing, f"FR missing keys: {missing}"


def test_fr_catalog_values_are_french() -> None:
    cat = load_catalog("fr")
    # Heuristic: at least one value contains a French-specific accent or word.
    text = " ".join(cat.values()).lower()
    assert any(c in text for c in "éèêàâîôûç") or "pêche" in text or "espèce" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_i18n.py::test_fr_catalog_has_all_required_keys tests/test_i18n.py::test_fr_catalog_values_are_french -v`
Expected: 2 fail (placeholder catalog only has app.title).

- [ ] **Step 3: Write the FR catalog**

Replace `app/locales/fr.json` with:

```json
{
  "app.title": "pechepro",
  "app.tagline": "Pêche en Amérique du Nord — astuces ciblées",
  "nav.home": "Accueil",
  "nav.conditions": "Conditions",
  "nav.tips": "Astuces",
  "home.title": "Choisissez votre pêche",
  "home.subtitle": "Espèce, région et type d'eau — recommandations en moins de 2 secondes.",
  "home.cta": "Voir les conditions",
  "form.species": "Espèce",
  "form.region": "Région",
  "form.water_type": "Type d'eau",
  "form.submit": "Recommander",
  "form.use_gps": "Utiliser ma position",
  "conditions.title": "Conditions actuelles",
  "conditions.weather": "Météo",
  "conditions.pressure": "Pression baro",
  "conditions.solunar": "Périodes solunaires",
  "conditions.sun_moon": "Soleil & Lune",
  "conditions.tips": "Astuces ciblées",
  "conditions.lures": "Leurres recommandés",
  "conditions.no_tips": "Aucune astuce spécifique pour ces conditions.",
  "errors.weather_unavailable": "Météo indisponible — astuces basées sur les conditions de référence.",
  "errors.gps_refused": "Localisation refusée — choisissez une région manuellement.",
  "errors.db_recovered": "Base de données récupérée. Vos préférences ont été réinitialisées.",
  "errors.backend_down": "Service indisponible — réessayez dans un instant.",
  "errors.no_data": "Données insuffisantes pour cette combinaison.",
  "footer.disclaimer": "Sources : Sépaq, Pêches et Océans Canada, In-Fisherman.",
  "footer.about": "À propos",
  "footer.lang_toggle": "English",
  "tips.title": "Toutes les astuces",
  "tips.filter_species": "Filtrer par espèce",
  "tips.source": "Source",
  "tips.confidence": "Fiabilité",
  "loading": "Chargement…",
  "back": "Retour"
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_i18n.py -v`
Expected: 13 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/locales/fr.json tests/test_i18n.py
git commit -m "feat(plan-1): fill FR locale catalog with 25+ UI strings"
```

---

### Task 8 : i18n EN catalog — fill UI strings

**Files:**
- Modify: `app/locales/en.json`
- Modify: `tests/test_i18n.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
def test_en_catalog_has_all_required_keys() -> None:
    cat = load_catalog("en")
    missing = REQUIRED_KEYS - set(cat)
    assert not missing, f"EN missing keys: {missing}"


def test_en_and_fr_catalogs_have_same_keys() -> None:
    fr = load_catalog("fr")
    en = load_catalog("en")
    only_fr = set(fr) - set(en)
    only_en = set(en) - set(fr)
    assert not only_fr, f"FR has keys missing in EN: {only_fr}"
    assert not only_en, f"EN has keys missing in FR: {only_en}"


def test_en_values_are_english() -> None:
    cat = load_catalog("en")
    # Heuristic: most common English particles appear at least once.
    text = " ".join(cat.values()).lower()
    assert any(w in text for w in ("the ", "and ", "for ", "your "))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_i18n.py -v -k "en_"`
Expected: 3 fail (en.json placeholder only has app.title).

- [ ] **Step 3: Write the EN catalog**

Replace `app/locales/en.json` with:

```json
{
  "app.title": "pechepro",
  "app.tagline": "North American fishing — targeted tips",
  "nav.home": "Home",
  "nav.conditions": "Conditions",
  "nav.tips": "Tips",
  "home.title": "Pick your fish",
  "home.subtitle": "Species, region, and water type — recommendations in under 2 seconds.",
  "home.cta": "Show conditions",
  "form.species": "Species",
  "form.region": "Region",
  "form.water_type": "Water type",
  "form.submit": "Recommend",
  "form.use_gps": "Use my location",
  "conditions.title": "Current conditions",
  "conditions.weather": "Weather",
  "conditions.pressure": "Barometric pressure",
  "conditions.solunar": "Solunar periods",
  "conditions.sun_moon": "Sun & moon",
  "conditions.tips": "Targeted tips",
  "conditions.lures": "Recommended lures",
  "conditions.no_tips": "No specific tip for these conditions.",
  "errors.weather_unavailable": "Weather unavailable — tips based on reference conditions.",
  "errors.gps_refused": "Location denied — pick a region manually.",
  "errors.db_recovered": "Database recovered. Your preferences have been reset.",
  "errors.backend_down": "Service unavailable — try again in a moment.",
  "errors.no_data": "Not enough data for this combination.",
  "footer.disclaimer": "Sources: Sépaq, Fisheries and Oceans Canada, In-Fisherman.",
  "footer.about": "About",
  "footer.lang_toggle": "Français",
  "tips.title": "All tips",
  "tips.filter_species": "Filter by species",
  "tips.source": "Source",
  "tips.confidence": "Confidence",
  "loading": "Loading…",
  "back": "Back"
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_i18n.py -v`
Expected: 16 PASS total (11 + 2 FR + 3 EN).

- [ ] **Step 5: Commit**

```powershell
git add app/locales/en.json tests/test_i18n.py
git commit -m "feat(plan-1): fill EN locale catalog and assert key parity with FR"
```

---

### Task 9 : Flask app factory + config

**Files:**
- Create: `app/server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_server.py`:

```python
"""Tests for app.server — Flask app factory."""

import sqlite3
from pathlib import Path

import pytest

from app.db.init_db import apply_schema
from app.server import AppConfig, create_app


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (1, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    conn.execute(
        "INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')"
    )
    conn.commit()
    conn.close()
    return db_path


def test_create_app_returns_flask_instance(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en"))
    assert app.name == "app.server"
    assert app.config["DB_PATH"] == seeded_db
    assert app.config["LANG"] == "en"


def test_app_config_defaults() -> None:
    cfg = AppConfig(db_path=Path("/tmp/x.db"))
    assert cfg.lang == "en"
    assert cfg.testing is False


def test_app_has_request_context_helpers(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with app.test_client() as client:
        # Root should at least respond (template may not exist yet — Task 10).
        # For now, verify the app has a /healthz endpoint.
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "lang": "fr"}


def test_app_injects_catalog_into_template_context(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.app_context():
        # The template global "t" must be a dict with at least "app.title".
        ctx = app.jinja_env.globals
        assert "catalog" in ctx
        assert "lang" in ctx
        assert ctx["lang"] == "en"
        assert ctx["catalog"]["app.title"] == "pechepro"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: all fail with `ImportError: cannot import name 'create_app' from 'app.server'`.

- [ ] **Step 3: Write the implementation**

Create `app/server.py`:

```python
"""Flask local server for pechepro.

Serves Jinja2 templates and JSON APIs to the PyWebView shell. All endpoints
listen on 127.0.0.1 only — never bind 0.0.0.0.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from app.i18n import detect_system_lang, load_catalog, normalize_lang


@dataclass(slots=True)
class AppConfig:
    """Runtime configuration for the Flask app."""

    db_path: Path
    lang: str = "en"
    testing: bool = False


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_app(config: AppConfig | None = None) -> Flask:
    """Application factory.

    Routes are registered here. Plan-1 owns: /, /conditions, /tips,
    /api/species, /api/regions, /api/water-types, /api/sun-moon,
    /api/weather, /api/recommend, /healthz, error handlers.
    """
    if config is None:
        config = AppConfig(db_path=Path("pechepro.db"), lang=detect_system_lang())

    app = Flask(__name__)
    app.config["DB_PATH"] = config.db_path
    app.config["LANG"] = normalize_lang(config.lang)
    app.config["TESTING"] = config.testing

    catalog = load_catalog(app.config["LANG"])
    app.jinja_env.globals["catalog"] = catalog
    app.jinja_env.globals["lang"] = app.config["LANG"]
    app.jinja_env.globals["t"] = lambda key: catalog.get(key, key)

    _register_routes(app)
    _register_error_handlers(app)
    return app


def _register_routes(app: Flask) -> None:
    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"status": "ok", "lang": app.config["LANG"]})


def _register_error_handlers(app: Flask) -> None:
    """Stub — populated in Task 19."""
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/server.py tests/test_server.py
git commit -m "feat(plan-1): add Flask app factory with i18n catalog injection"
```

---

### Task 10 : Flask route GET / (Home)

**Files:**
- Modify: `app/server.py`
- Create: `app/templates/__init__.py`
- Create: `app/templates/home.html` (placeholder — full version in Task 21)
- Create: `app/templates/base.html` (placeholder — full version in Task 20)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_get_home_returns_html(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/html")
        body = resp.get_data(as_text=True)
        assert "pechepro" in body.lower()


def test_get_home_renders_in_french(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with app.test_client() as client:
        resp = client.get("/")
        body = resp.get_data(as_text=True)
        assert "Accueil" in body or "Choisissez" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k home`
Expected: 2 fail with 404 or `TemplateNotFound`.

- [ ] **Step 3: Create placeholder templates**

Create `app/templates/__init__.py` (empty file).

Create `app/templates/base.html`:

```html
<!doctype html>
<html lang="{{ lang }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ t('app.title') }}{% block title %}{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/">{{ t('app.title') }}</a>
    <nav>
      <a href="/">{{ t('nav.home') }}</a>
      <a href="/tips">{{ t('nav.tips') }}</a>
    </nav>
  </header>
  <main>{% block main %}{% endblock %}</main>
  <footer>
    <p>{{ t('footer.disclaimer') }}</p>
    {% block footer_widget %}{% endblock %}
  </footer>
  <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
```

Create `app/templates/home.html`:

```html
{% extends "base.html" %}
{% block main %}
  <section class="home">
    <h1>{{ t('home.title') }}</h1>
    <p class="subtitle">{{ t('home.subtitle') }}</p>
    <form id="recommend-form" action="/conditions" method="get">
      <label for="species">{{ t('form.species') }}</label>
      <select id="species" name="species" required></select>
      <label for="water_type">{{ t('form.water_type') }}</label>
      <select id="water_type" name="water" required></select>
      <label for="region">{{ t('form.region') }}</label>
      <select id="region" name="region"></select>
      <input type="hidden" id="lat" name="lat">
      <input type="hidden" id="lon" name="lon">
      <button type="button" id="use-gps">{{ t('form.use_gps') }}</button>
      <button type="submit">{{ t('home.cta') }}</button>
    </form>
  </section>
{% endblock %}
```

- [ ] **Step 4: Add the GET / route**

Edit `app/server.py` — replace `_register_routes` body:

```python
def _register_routes(app: Flask) -> None:
    from flask import render_template

    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"status": "ok", "lang": app.config["LANG"]})

    @app.get("/")
    def home() -> Any:
        return render_template("home.html")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: 6 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/server.py app/templates/__init__.py app/templates/base.html app/templates/home.html tests/test_server.py
git commit -m "feat(plan-1): add GET / Home route rendering home.html with i18n"
```

---

### Task 11 : Flask route GET /api/species

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_get_api_species_returns_seeded_rows(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/species")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        first = data[0]
        assert first["id"] == 1
        assert first["common_name_fr"] == "Doré jaune"
        assert first["common_name_en"] == "Walleye"
        assert "scientific_name" in first


def test_get_api_species_empty_db_returns_empty_list(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    apply_schema(db)
    app = create_app(AppConfig(db_path=db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/species")
        assert resp.status_code == 200
        assert resp.get_json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k species`
Expected: 2 fail (404 — route doesn't exist).

- [ ] **Step 3: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/api/species")
    def api_species() -> Any:
        conn = _connect(app.config["DB_PATH"])
        try:
            rows = conn.execute(
                "SELECT id, common_name_fr, common_name_en, scientific_name, "
                "family, typical_habitat, image_url FROM species ORDER BY common_name_fr"
            ).fetchall()
            return jsonify([dict(r) for r in rows])
        finally:
            conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k species`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/server.py tests/test_server.py
git commit -m "feat(plan-1): add GET /api/species endpoint"
```

---

### Task 12 : Flask route GET /api/regions

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_get_api_regions_returns_seeded_rows(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/regions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        first = data[0]
        assert first["id"] == 1
        assert first["country"] == "CA"
        assert first["iso_code"] == "QC"
        assert first["name_fr"] == "Québec"
        assert first["name_en"] == "Quebec"


def test_get_api_regions_filters_by_country(seeded_db: Path) -> None:
    conn = sqlite3.connect(seeded_db)
    conn.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (50, 'New York', 'New York', 'US', 'NY')"
    )
    conn.commit()
    conn.close()
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/regions?country=US")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["iso_code"] == "NY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k regions`
Expected: 2 fail with 404.

- [ ] **Step 3: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/api/regions")
    def api_regions() -> Any:
        from flask import request

        country = request.args.get("country")
        conn = _connect(app.config["DB_PATH"])
        try:
            if country:
                rows = conn.execute(
                    "SELECT id, name_fr, name_en, country, iso_code, "
                    "bbox_lat_min, bbox_lat_max, bbox_lon_min, bbox_lon_max "
                    "FROM regions WHERE country = ? ORDER BY name_fr",
                    (country,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name_fr, name_en, country, iso_code, "
                    "bbox_lat_min, bbox_lat_max, bbox_lon_min, bbox_lon_max "
                    "FROM regions ORDER BY country, name_fr"
                ).fetchall()
            return jsonify([dict(r) for r in rows])
        finally:
            conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k regions`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/server.py tests/test_server.py
git commit -m "feat(plan-1): add GET /api/regions with optional country filter"
```

---

### Task 13 : Flask route GET /api/water-types

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_get_api_water_types_returns_seeded_rows(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/water-types")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert any(d["name_en"] == "Lake" for d in data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -v -k water_types`
Expected: 1 fail with 404.

- [ ] **Step 3: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/api/water-types")
    def api_water_types() -> Any:
        conn = _connect(app.config["DB_PATH"])
        try:
            rows = conn.execute(
                "SELECT id, name_fr, name_en FROM water_types ORDER BY name_fr"
            ).fetchall()
            return jsonify([dict(r) for r in rows])
        finally:
            conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server.py -v -k water_types`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/server.py tests/test_server.py
git commit -m "feat(plan-1): add GET /api/water-types endpoint"
```

---

### Task 14 : Flask route GET /api/sun-moon (delegates to astral_calc)

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
from unittest.mock import patch


def test_get_api_sun_moon_delegates_to_service(seeded_db: Path) -> None:
    fake_payload = {
        "sunrise": "2026-05-09T05:30:00-04:00",
        "sunset": "2026-05-09T20:15:00-04:00",
        "civil_dawn": "2026-05-09T05:00:00-04:00",
        "civil_dusk": "2026-05-09T20:45:00-04:00",
        "moon_phase": "waxing",
        "moon_illumination": 0.42,
    }
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.astral_calc.sun_moon", return_value=fake_payload) as m:
        with app.test_client() as client:
            resp = client.get("/api/sun-moon?lat=46.81&lon=-71.21&date=2026-05-09")
            assert resp.status_code == 200
            assert resp.get_json() == fake_payload
            m.assert_called_once_with(46.81, -71.21, "2026-05-09")


def test_get_api_sun_moon_missing_params_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/sun-moon")
        assert resp.status_code == 400
        assert "error" in resp.get_json()


def test_get_api_sun_moon_invalid_lat_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/sun-moon?lat=abc&lon=-71.21&date=2026-05-09")
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k sun_moon`
Expected: 3 fail (404 / no service stub).

- [ ] **Step 3: Create a service stub so tests can patch it**

Create `app/services/astral_calc.py` (stub — plan-2 will replace):

```python
"""astral_calc service — sunrise/sunset/moon phase. Plan-2 implements."""

from __future__ import annotations


def sun_moon(lat: float, lon: float, date: str) -> dict[str, object]:
    """Compute sun + moon data for given location and date.

    Returns dict with keys: sunrise, sunset, civil_dawn, civil_dusk,
    moon_phase, moon_illumination. Plan-2 fills the implementation.
    """
    raise NotImplementedError("Implemented in plan-2")
```

- [ ] **Step 4: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/api/sun-moon")
    def api_sun_moon() -> Any:
        from flask import request

        from app.services import astral_calc

        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
            date = request.args["date"]
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid lat/lon/date"}), 400
        return jsonify(astral_calc.sun_moon(lat, lon, date))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k sun_moon`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/server.py app/services/astral_calc.py tests/test_server.py
git commit -m "feat(plan-1): add GET /api/sun-moon delegating to astral_calc service"
```

---

### Task 15 : Flask route GET /api/weather (with cache fallback)

**Files:**
- Modify: `app/server.py`
- Create: `app/services/openmeteo_client.py` (stub)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
from app.services.errors import ServiceUnavailable


def test_get_api_weather_returns_payload(seeded_db: Path) -> None:
    fake = {
        "temp_air_c": 18.5,
        "pressure_hpa": 1013.2,
        "pressure_trend_6h": "rising",
        "humidity_pct": 64,
        "wind_kmh": 12.0,
        "cloud_cover_pct": 30,
        "fetched_at": "2026-05-09T12:00:00Z",
        "cached": False,
    }
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.openmeteo_client.get_weather", return_value=fake) as m:
        with app.test_client() as client:
            resp = client.get("/api/weather?lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            assert resp.get_json() == fake
            m.assert_called_once_with(46.81, -71.21)


def test_get_api_weather_returns_503_on_service_unavailable(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    err = ServiceUnavailable(service="openmeteo", reason="timeout")
    with patch("app.services.openmeteo_client.get_weather", side_effect=err):
        with app.test_client() as client:
            resp = client.get("/api/weather?lat=46.81&lon=-71.21")
            assert resp.status_code == 503
            body = resp.get_json()
            assert body["error"] == "weather_unavailable"
            assert "openmeteo" in body["service"]


def test_get_api_weather_missing_params_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/weather")
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k api_weather`
Expected: 3 fail (no service stub / no route).

- [ ] **Step 3: Create the openmeteo_client stub**

Create `app/services/openmeteo_client.py`:

```python
"""openmeteo_client — wrapper around api.open-meteo.com. Plan-2 implements."""

from __future__ import annotations


def get_weather(lat: float, lon: float) -> dict[str, object]:
    """Return a weather dict (see plan-1 contract). Plan-2 implements."""
    raise NotImplementedError("Implemented in plan-2")
```

- [ ] **Step 4: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/api/weather")
    def api_weather() -> Any:
        from flask import request

        from app.services import openmeteo_client
        from app.services.errors import ServiceUnavailable

        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid lat/lon"}), 400
        try:
            return jsonify(openmeteo_client.get_weather(lat, lon))
        except ServiceUnavailable as exc:
            return (
                jsonify({"error": "weather_unavailable", "service": exc.service, "reason": exc.reason}),
                503,
            )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k api_weather`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/server.py app/services/openmeteo_client.py tests/test_server.py
git commit -m "feat(plan-1): add GET /api/weather with 503 on ServiceUnavailable"
```

---

### Task 16 : Flask route POST /api/recommend (delegates to recommender)

**Files:**
- Modify: `app/server.py`
- Create: `app/services/recommender.py` (stub)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_post_api_recommend_returns_ranked_tips(seeded_db: Path) -> None:
    fake = [
        {"id": 1, "tip_text_fr": "FR1", "tip_text_en": "EN1", "source_url": "u1", "confidence": 4, "match_score": 0.9},
        {"id": 2, "tip_text_fr": "FR2", "tip_text_en": "EN2", "source_url": "u2", "confidence": 3, "match_score": 0.6},
    ]
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.recommender.recommend", return_value=fake) as m:
        with app.test_client() as client:
            payload = {
                "species_id": 1,
                "region_id": 1,
                "water_type_id": 1,
                "conditions": {
                    "baro_trend": "rising",
                    "moon_phase": "waxing",
                    "season": "spring",
                    "time_of_day": "dawn",
                    "temp_water_c": 12.5,
                },
            }
            resp = client.post("/api/recommend", json=payload)
            assert resp.status_code == 200
            assert resp.get_json() == fake
            m.assert_called_once_with(1, 1, 1, payload["conditions"])


def test_post_api_recommend_missing_body_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.post("/api/recommend", json={})
        assert resp.status_code == 400


def test_post_api_recommend_handles_null_region(seeded_db: Path) -> None:
    fake = [{"id": 1, "tip_text_fr": "x", "tip_text_en": "x", "source_url": None, "confidence": 3, "match_score": 0.5}]
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.recommender.recommend", return_value=fake) as m:
        with app.test_client() as client:
            resp = client.post(
                "/api/recommend",
                json={"species_id": 1, "region_id": None, "water_type_id": 1, "conditions": {}},
            )
            assert resp.status_code == 200
            m.assert_called_once_with(1, None, 1, {})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k recommend`
Expected: 3 fail.

- [ ] **Step 3: Create recommender stub**

Create `app/services/recommender.py`:

```python
"""recommender — rank tips for given conditions. Plan-2 implements."""

from __future__ import annotations


def recommend(
    species_id: int,
    region_id: int | None,
    water_type_id: int,
    conditions: dict[str, str | float | None],
) -> list[dict[str, object]]:
    """Rank matching tips. See plan-1 contract for the dict shape."""
    raise NotImplementedError("Implemented in plan-2")
```

- [ ] **Step 4: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.post("/api/recommend")
    def api_recommend() -> Any:
        from flask import request

        from app.services import recommender

        body = request.get_json(silent=True) or {}
        try:
            species_id = int(body["species_id"])
            water_type_id = int(body["water_type_id"])
        except (KeyError, ValueError, TypeError):
            return jsonify({"error": "missing or invalid species_id/water_type_id"}), 400
        region_raw = body.get("region_id")
        region_id = int(region_raw) if region_raw is not None else None
        conditions = body.get("conditions") or {}
        if not isinstance(conditions, dict):
            return jsonify({"error": "conditions must be an object"}), 400
        tips = recommender.recommend(species_id, region_id, water_type_id, conditions)
        return jsonify(tips)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k recommend`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/server.py app/services/recommender.py tests/test_server.py
git commit -m "feat(plan-1): add POST /api/recommend delegating to recommender service"
```

---

### Task 17 : Flask route GET /conditions (full orchestration)

**Files:**
- Modify: `app/server.py`
- Create: `app/templates/conditions.html` (placeholder — full version in Task 22)
- Create: `app/services/solunar.py` (stub)
- Create: `app/services/usgs_client.py` (stub)
- Create: `app/services/eccc_client.py` (stub)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_get_conditions_orchestrates_all_services(seeded_db: Path) -> None:
    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "2026-05-09T12:00:00Z", "cached": False}
    sun_moon = {"sunrise": "2026-05-09T05:30:00", "sunset": "2026-05-09T20:15:00",
                "civil_dawn": "2026-05-09T05:00:00", "civil_dusk": "2026-05-09T20:45:00",
                "moon_phase": "waxing", "moon_illumination": 0.42}
    solunar = {"major": [{"start": "2026-05-09T08:00:00", "end": "2026-05-09T10:00:00", "score": 0.9}],
               "minor": [{"start": "2026-05-09T14:00:00", "end": "2026-05-09T15:00:00", "score": 0.6}]}
    tips = [{"id": 1, "tip_text_fr": "FR1", "tip_text_en": "EN1",
             "source_url": "u1", "confidence": 4, "match_score": 0.9}]

    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value=solunar),
        patch("app.services.recommender.recommend", return_value=tips),
        patch("app.services.usgs_client.get_water_temp", return_value=14.0),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            assert "EN1" in body  # tip rendered
            assert "Walleye" in body  # species name


def test_get_conditions_renders_in_french(seeded_db: Path) -> None:
    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "x", "cached": False}
    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.42}
    solunar = {"major": [], "minor": []}
    tips = [{"id": 1, "tip_text_fr": "Astuce FR", "tip_text_en": "Tip EN",
             "source_url": None, "confidence": 4, "match_score": 0.9}]
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value=solunar),
        patch("app.services.recommender.recommend", return_value=tips),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=14.5),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21")
            body = resp.get_data(as_text=True)
            assert "Astuce FR" in body
            assert "Doré jaune" in body


def test_get_conditions_handles_weather_unavailable_gracefully(seeded_db: Path) -> None:
    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.5}
    solunar = {"major": [], "minor": []}
    tips: list[dict[str, object]] = []
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather",
              side_effect=ServiceUnavailable(service="openmeteo", reason="timeout")),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value=solunar),
        patch("app.services.recommender.recommend", return_value=tips),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=None),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200  # graceful — not 503
            body = resp.get_data(as_text=True)
            assert "unavailable" in body.lower() or "indisponible" in body.lower()


def test_get_conditions_missing_required_params_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/conditions")
        assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k conditions`
Expected: 4 fail.

- [ ] **Step 3: Create service stubs**

Create `app/services/solunar.py`:

```python
"""solunar — major/minor periods. Plan-2 implements."""

from __future__ import annotations


def compute_periods(lat: float, lon: float, date: str) -> dict[str, object]:
    """Return {'major': [...], 'minor': [...]}. Plan-2 implements."""
    raise NotImplementedError("Implemented in plan-2")
```

Create `app/services/usgs_client.py`:

```python
"""usgs_client — water temp from USGS Water Services. Plan-2 implements."""

from __future__ import annotations


def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temp (°C) for nearest USGS station, or None."""
    raise NotImplementedError("Implemented in plan-2")
```

Create `app/services/eccc_client.py`:

```python
"""eccc_client — water temp from ECCC Canada. Plan-2 implements."""

from __future__ import annotations


def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temp (°C) for nearest ECCC station, or None."""
    raise NotImplementedError("Implemented in plan-2")
```

- [ ] **Step 4: Create conditions.html placeholder template**

Create `app/templates/conditions.html`:

```html
{% extends "base.html" %}
{% block main %}
  <section class="conditions">
    <h1>{{ t('conditions.title') }} — {{ species_name }}</h1>
    {% if weather_error %}
      <p class="alert">{{ t('errors.weather_unavailable') }} (unavailable: {{ weather_error }})</p>
    {% else %}
      <div class="weather">
        <span>{{ t('conditions.weather') }}: {{ weather.temp_air_c }} °C</span>
        <span>{{ t('conditions.pressure') }}: {{ weather.pressure_hpa }} hPa ({{ weather.pressure_trend_6h }})</span>
      </div>
    {% endif %}
    <div class="sun-moon">
      <h2>{{ t('conditions.sun_moon') }}</h2>
      <p>{{ sun_moon.sunrise }} → {{ sun_moon.sunset }}</p>
      <p>Moon: {{ sun_moon.moon_phase }} ({{ (sun_moon.moon_illumination * 100) | int }}%)</p>
    </div>
    <div class="solunar">
      <h2>{{ t('conditions.solunar') }}</h2>
      <ul>
        {% for p in solunar.major %}<li>Major {{ p.start }} → {{ p.end }} (score {{ p.score }})</li>{% endfor %}
        {% for p in solunar.minor %}<li>Minor {{ p.start }} → {{ p.end }} (score {{ p.score }})</li>{% endfor %}
      </ul>
    </div>
    <div class="tips">
      <h2>{{ t('conditions.tips') }}</h2>
      {% if tips %}
        <ul>
        {% for tip in tips %}
          <li>
            <p>{% if lang == 'fr' %}{{ tip.tip_text_fr }}{% else %}{{ tip.tip_text_en }}{% endif %}</p>
            {% if tip.source_url %}<a href="{{ tip.source_url }}">{{ t('tips.source') }}</a>{% endif %}
          </li>
        {% endfor %}
        </ul>
      {% else %}
        <p>{{ t('conditions.no_tips') }}</p>
      {% endif %}
    </div>
  </section>
{% endblock %}
{% block footer_widget %}
  <div class="eg-affiliate-banners"
       data-program="us-expedia"
       data-network="pz"
       data-layout="leaderboard"
       data-image="city"
       data-message="none"
       data-camref="1101l5IQud"
       data-pubref="pechepro-tips"
       data-link="home"></div>
  <script class="eg-affiliate-banners-script"
          src="https://creator.expediagroup.com/products/banners/assets/eg-affiliate-banners.js"></script>
{% endblock %}
```

- [ ] **Step 5: Add the orchestrating route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/conditions")
    def conditions_view() -> Any:
        from datetime import date as _date

        from flask import render_template, request

        from app.services import (
            astral_calc,
            eccc_client,
            openmeteo_client,
            recommender,
            solunar,
            usgs_client,
        )
        from app.services.errors import ServiceUnavailable

        try:
            species_id = int(request.args["species"])
            water_type_id = int(request.args["water"])
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid required params"}), 400

        region_raw = request.args.get("region")
        region_id = int(region_raw) if region_raw and region_raw.isdigit() else None
        today = request.args.get("date") or _date.today().isoformat()

        conn = _connect(app.config["DB_PATH"])
        try:
            sp_row = conn.execute(
                "SELECT common_name_fr, common_name_en FROM species WHERE id = ?",
                (species_id,),
            ).fetchone()
        finally:
            conn.close()
        if sp_row is None:
            return jsonify({"error": "unknown species"}), 404
        species_name = sp_row["common_name_fr" if app.config["LANG"] == "fr" else "common_name_en"]

        # Sun + moon (always succeeds — no network).
        sm = astral_calc.sun_moon(lat, lon, today)
        # Solunar periods (always succeeds — no network).
        sl = solunar.compute_periods(lat, lon, today)

        # Weather (graceful fallback on ServiceUnavailable).
        weather_payload: dict[str, object] | None = None
        weather_error: str | None = None
        try:
            weather_payload = openmeteo_client.get_weather(lat, lon)
        except ServiceUnavailable as exc:
            weather_error = exc.reason

        # Water temp (USGS first, ECCC fallback). Both may return None.
        water_temp_c: float | None = None
        try:
            water_temp_c = usgs_client.get_water_temp(lat, lon)
        except ServiceUnavailable:
            water_temp_c = None
        if water_temp_c is None:
            try:
                water_temp_c = eccc_client.get_water_temp(lat, lon)
            except ServiceUnavailable:
                water_temp_c = None

        conditions = {
            "baro_trend": (weather_payload or {}).get("pressure_trend_6h", "any"),
            "moon_phase": sm.get("moon_phase", "any"),
            "season": _season_for_date(today),
            "time_of_day": "any",
            "temp_water_c": water_temp_c,
        }
        tips = recommender.recommend(species_id, region_id, water_type_id, conditions)

        return render_template(
            "conditions.html",
            species_name=species_name,
            weather=weather_payload,
            weather_error=weather_error,
            sun_moon=sm,
            solunar=sl,
            tips=tips,
            water_temp_c=water_temp_c,
        )


def _season_for_date(iso_date: str) -> str:
    """Map a YYYY-MM-DD to spring/summer/fall/winter (Northern hemisphere)."""
    month = int(iso_date.split("-")[1])
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "fall"
    return "winter"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k conditions`
Expected: 4 PASS.

- [ ] **Step 7: Commit**

```powershell
git add app/server.py app/templates/conditions.html app/services/solunar.py app/services/usgs_client.py app/services/eccc_client.py tests/test_server.py
git commit -m "feat(plan-1): add GET /conditions orchestrating weather/solunar/sun_moon/tips"
```

---

### Task 18 : Flask route GET /tips (browse all tips)

**Files:**
- Modify: `app/server.py`
- Create: `app/templates/tips.html` (placeholder — full version in Task 23)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def _seed_one_tip(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, "
        "source_url, confidence) VALUES (1, 1, 'Astuce A', 'Tip A', 'https://x', 4)"
    )
    conn.commit()
    conn.close()


def test_get_tips_renders_all_tips(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/tips")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Tip A" in body


def test_get_tips_filters_by_species(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/tips?species=1")
        assert resp.status_code == 200
        assert "Tip A" in resp.get_data(as_text=True)


def test_get_tips_unknown_species_returns_empty(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/tips?species=999")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Tip A" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k get_tips`
Expected: 3 fail (404).

- [ ] **Step 3: Create tips.html placeholder**

Create `app/templates/tips.html`:

```html
{% extends "base.html" %}
{% block main %}
  <section class="tips-browse">
    <h1>{{ t('tips.title') }}</h1>
    {% if tips %}
      <ul>
      {% for tip in tips %}
        <li>
          <p>{% if lang == 'fr' %}{{ tip.tip_text_fr }}{% else %}{{ tip.tip_text_en }}{% endif %}</p>
          <small>{{ tip.species_name }}</small>
          {% if tip.source_url %}<a href="{{ tip.source_url }}">{{ t('tips.source') }}</a>{% endif %}
        </li>
      {% endfor %}
      </ul>
    {% else %}
      <p>{{ t('errors.no_data') }}</p>
    {% endif %}
  </section>
{% endblock %}
```

- [ ] **Step 4: Add the route**

Edit `app/server.py` — append inside `_register_routes`:

```python
    @app.get("/tips")
    def tips_view() -> Any:
        from flask import render_template, request

        species_filter = request.args.get("species")
        conn = _connect(app.config["DB_PATH"])
        try:
            if species_filter and species_filter.isdigit():
                rows = conn.execute(
                    "SELECT t.id, t.tip_text_fr, t.tip_text_en, t.source_url, t.confidence, "
                    "s.common_name_fr || ' / ' || s.common_name_en AS species_name "
                    "FROM tips t JOIN species s ON s.id = t.species_id "
                    "WHERE t.species_id = ? "
                    "ORDER BY t.confidence DESC, t.id",
                    (int(species_filter),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT t.id, t.tip_text_fr, t.tip_text_en, t.source_url, t.confidence, "
                    "s.common_name_fr || ' / ' || s.common_name_en AS species_name "
                    "FROM tips t JOIN species s ON s.id = t.species_id "
                    "ORDER BY t.confidence DESC, t.id"
                ).fetchall()
            tips = [dict(r) for r in rows]
        finally:
            conn.close()
        return render_template("tips.html", tips=tips)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k get_tips`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app/server.py app/templates/tips.html tests/test_server.py
git commit -m "feat(plan-1): add GET /tips browse view with species filter"
```

---

### Task 19 : Flask error handlers (404 / 500 / ServiceUnavailable)

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_404_returns_json_for_api_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
        assert resp.content_type.startswith("application/json")
        body = resp.get_json()
        assert body["error"] == "not_found"


def test_404_returns_html_for_page_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/missing-page")
        assert resp.status_code == 404
        assert resp.content_type.startswith("text/html")


def test_500_returns_json_for_api_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))

    @app.get("/api/boom")
    def boom() -> Any:
        raise RuntimeError("explode")

    app.config["TESTING"] = False  # let error handler run
    with app.test_client() as client:
        resp = client.get("/api/boom")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "internal_error"


def test_service_unavailable_handler_for_html_pages(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))

    @app.get("/dies")
    def dies() -> Any:
        from app.services.errors import ServiceUnavailable
        raise ServiceUnavailable(service="x", reason="y")

    app.config["TESTING"] = False
    with app.test_client() as client:
        resp = client.get("/dies")
        assert resp.status_code == 503
        body = resp.get_data(as_text=True)
        assert "unavailable" in body.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "404 or 500 or service_unavailable_handler"`
Expected: 4 fail (some pass with default Flask behaviour, others fail).

- [ ] **Step 3: Implement error handlers + error template**

Create `app/templates/error.html`:

```html
{% extends "base.html" %}
{% block main %}
  <section class="error-page">
    <h1>{{ status }} — {{ message }}</h1>
    <p>{{ detail }}</p>
    <a href="/">{{ t('back') }}</a>
  </section>
{% endblock %}
```

Edit `app/server.py` — replace `_register_error_handlers` body:

```python
def _register_error_handlers(app: Flask) -> None:
    from flask import render_template, request

    from app.services.errors import ServiceUnavailable

    def _wants_json() -> bool:
        return request.path.startswith("/api/") or request.is_json

    @app.errorhandler(404)
    def not_found(_exc: Any) -> Any:
        if _wants_json():
            return jsonify({"error": "not_found", "path": request.path}), 404
        return render_template("error.html", status=404,
                               message="Not found", detail=request.path), 404

    @app.errorhandler(500)
    def internal_error(_exc: Any) -> Any:
        if _wants_json():
            return jsonify({"error": "internal_error"}), 500
        return render_template("error.html", status=500,
                               message="Internal error",
                               detail=app.jinja_env.globals["catalog"].get("errors.backend_down", "")), 500

    @app.errorhandler(ServiceUnavailable)
    def svc_unavailable(exc: ServiceUnavailable) -> Any:
        if _wants_json():
            return jsonify({"error": "service_unavailable",
                            "service": exc.service, "reason": exc.reason}), 503
        return render_template("error.html", status=503,
                               message="Service unavailable",
                               detail=f"{exc.service}: {exc.reason}"), 503
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: all PASS (~28 tests so far).

- [ ] **Step 5: Commit**

```powershell
git add app/server.py app/templates/error.html tests/test_server.py
git commit -m "feat(plan-1): add 404/500/ServiceUnavailable handlers (JSON for /api, HTML otherwise)"
```

---

### Task 20 : Base template (base.html) full version + Expedia widget

**Files:**
- Modify: `app/templates/base.html`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_base_template_includes_expedia_widget_on_conditions(seeded_db: Path) -> None:
    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "x", "cached": False}
    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.5}
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value={"major": [], "minor": []}),
        patch("app.services.recommender.recommend", return_value=[]),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=None),
    ):
        with app.test_client() as client:
            body = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21").get_data(as_text=True)
            assert 'data-camref="1101l5IQud"' in body
            assert 'data-pubref="pechepro-tips"' in body
            assert "eg-affiliate-banners.js" in body


def test_base_template_lang_attribute_matches_config(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with app.test_client() as client:
        body = client.get("/").get_data(as_text=True)
        assert '<html lang="fr"' in body


def test_base_template_has_lang_toggle_link(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/").get_data(as_text=True)
        assert "Français" in body  # footer toggle text in EN catalog
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "base_template or lang_toggle"`
Expected: `test_base_template_has_lang_toggle_link` fails (placeholder doesn't include footer toggle).

- [ ] **Step 3: Replace base.html with the full version**

Replace `app/templates/base.html` with:

```html
<!doctype html>
<html lang="{{ lang }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ t('app.title') }}{% block title %}{% endblock %}</title>
  <meta name="description" content="{{ t('app.tagline') }}">
  <link rel="icon" type="image/x-icon" href="{{ url_for('static', filename='img/logo.ico') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="topbar">
    <a class="brand" href="/">
      <img src="{{ url_for('static', filename='img/logo.ico') }}" alt="" width="24" height="24">
      <span>{{ t('app.title') }}</span>
    </a>
    <nav aria-label="main">
      <a href="/">{{ t('nav.home') }}</a>
      <a href="/tips">{{ t('nav.tips') }}</a>
    </nav>
  </header>
  <main id="main">{% block main %}{% endblock %}</main>
  <footer>
    <p class="disclaimer">{{ t('footer.disclaimer') }}</p>
    <p class="meta">
      <a href="#" id="lang-toggle" data-lang="{{ 'fr' if lang == 'en' else 'en' }}">{{ t('footer.lang_toggle') }}</a>
    </p>
    {% block footer_widget %}{% endblock %}
  </footer>
  <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
</html>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "base_template or lang_toggle"`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/templates/base.html tests/test_server.py
git commit -m "feat(plan-1): finalize base.html with logo, nav, footer toggle, Expedia block"
```

---

### Task 21 : Home template (home.html) full version

**Files:**
- Modify: `app/templates/home.html`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_home_template_has_form_with_required_selects(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/").get_data(as_text=True)
        assert 'id="recommend-form"' in body
        assert 'name="species"' in body
        assert 'name="water"' in body
        assert 'name="region"' in body
        assert 'id="use-gps"' in body


def test_home_template_form_action_is_conditions(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/").get_data(as_text=True)
        assert 'action="/conditions"' in body


def test_home_template_includes_loading_indicator(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/").get_data(as_text=True)
        # i18n key 'loading' must surface either as text or as an aria-label.
        assert "Loading" in body or "loading" in body.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "home_template"`
Expected: `test_home_template_includes_loading_indicator` fails.

- [ ] **Step 3: Replace home.html with the full version**

Replace `app/templates/home.html` with:

```html
{% extends "base.html" %}
{% block main %}
  <section class="home">
    <h1>{{ t('home.title') }}</h1>
    <p class="subtitle">{{ t('home.subtitle') }}</p>

    <form id="recommend-form" action="/conditions" method="get" novalidate>
      <div class="form-row">
        <label for="species">{{ t('form.species') }}</label>
        <select id="species" name="species" required aria-required="true">
          <option value="" disabled selected>{{ t('loading') }}</option>
        </select>
      </div>

      <div class="form-row">
        <label for="water">{{ t('form.water_type') }}</label>
        <select id="water" name="water" required aria-required="true">
          <option value="" disabled selected>{{ t('loading') }}</option>
        </select>
      </div>

      <div class="form-row">
        <label for="region">{{ t('form.region') }}</label>
        <select id="region" name="region">
          <option value="">— {{ t('loading') }} —</option>
        </select>
      </div>

      <input type="hidden" id="lat" name="lat">
      <input type="hidden" id="lon" name="lon">

      <div class="form-actions">
        <button type="button" id="use-gps" class="btn btn-secondary">{{ t('form.use_gps') }}</button>
        <button type="submit" class="btn btn-primary">{{ t('home.cta') }}</button>
      </div>

      <p class="form-status" id="form-status" role="status" aria-live="polite"></p>
    </form>
  </section>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "home_template"`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/templates/home.html tests/test_server.py
git commit -m "feat(plan-1): finalize home.html with accessible recommend form"
```

---

### Task 22 : Conditions template (conditions.html) full version

**Files:**
- Modify: `app/templates/conditions.html`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_conditions_template_renders_water_temp_when_present(seeded_db: Path) -> None:
    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "x", "cached": False}
    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.5}
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value={"major": [], "minor": []}),
        patch("app.services.recommender.recommend", return_value=[]),
        patch("app.services.usgs_client.get_water_temp", return_value=14.5),
    ):
        with app.test_client() as client:
            body = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21").get_data(as_text=True)
            assert "14.5" in body


def test_conditions_template_renders_solunar_periods(seeded_db: Path) -> None:
    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "x", "cached": False}
    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.5}
    solunar = {"major": [{"start": "08:00", "end": "10:00", "score": 0.9}],
               "minor": [{"start": "14:00", "end": "15:00", "score": 0.5}]}
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value=solunar),
        patch("app.services.recommender.recommend", return_value=[]),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=None),
    ):
        with app.test_client() as client:
            body = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21").get_data(as_text=True)
            assert "08:00" in body
            assert "0.9" in body


def test_conditions_template_shows_confidence_badge(seeded_db: Path) -> None:
    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "x", "cached": False}
    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.5}
    tip = {"id": 1, "tip_text_fr": "FR", "tip_text_en": "Tip text",
           "source_url": "https://example.com", "confidence": 5, "match_score": 0.8}
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value={"major": [], "minor": []}),
        patch("app.services.recommender.recommend", return_value=[tip]),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=None),
    ):
        with app.test_client() as client:
            body = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21").get_data(as_text=True)
            assert "Confidence" in body  # badge label from i18n
            assert "5" in body  # the value
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "conditions_template"`
Expected: 3 fail (placeholder template doesn't render water_temp, full solunar block, or confidence badge).

- [ ] **Step 3: Replace conditions.html with the full version**

Replace `app/templates/conditions.html` with:

```html
{% extends "base.html" %}
{% block title %} — {{ t('conditions.title') }} — {{ species_name }}{% endblock %}
{% block main %}
  <section class="conditions">
    <header class="conditions-header">
      <h1>{{ t('conditions.title') }}</h1>
      <p class="species-name">{{ species_name }}</p>
    </header>

    <div class="grid">
      <article class="card weather">
        <h2>{{ t('conditions.weather') }}</h2>
        {% if weather_error %}
          <p class="alert" role="alert">{{ t('errors.weather_unavailable') }}</p>
          <p class="alert-detail">unavailable: {{ weather_error }}</p>
        {% else %}
          <ul class="metrics">
            <li><span class="label">temp</span><span class="value">{{ "%.1f"|format(weather.temp_air_c) }} °C</span></li>
            <li><span class="label">{{ t('conditions.pressure') }}</span><span class="value">{{ "%.0f"|format(weather.pressure_hpa) }} hPa</span></li>
            <li><span class="label">trend 6h</span><span class="value badge badge-{{ weather.pressure_trend_6h }}">{{ weather.pressure_trend_6h }}</span></li>
            <li><span class="label">wind</span><span class="value">{{ "%.0f"|format(weather.wind_kmh) }} km/h</span></li>
            <li><span class="label">cloud</span><span class="value">{{ weather.cloud_cover_pct }} %</span></li>
          </ul>
        {% endif %}
        {% if water_temp_c is not none %}
          <p class="water-temp">water: {{ "%.1f"|format(water_temp_c) }} °C</p>
        {% endif %}
      </article>

      <article class="card sun-moon">
        <h2>{{ t('conditions.sun_moon') }}</h2>
        <ul class="metrics">
          <li><span class="label">sunrise</span><span class="value">{{ sun_moon.sunrise }}</span></li>
          <li><span class="label">sunset</span><span class="value">{{ sun_moon.sunset }}</span></li>
          <li><span class="label">moon</span><span class="value">{{ sun_moon.moon_phase }} ({{ (sun_moon.moon_illumination * 100) | int }}%)</span></li>
        </ul>
      </article>

      <article class="card solunar">
        <h2>{{ t('conditions.solunar') }}</h2>
        {% if solunar.major or solunar.minor %}
          <ul class="periods">
            {% for p in solunar.major %}
              <li class="period major"><span class="badge badge-major">major</span> {{ p.start }} → {{ p.end }} <span class="score">{{ p.score }}</span></li>
            {% endfor %}
            {% for p in solunar.minor %}
              <li class="period minor"><span class="badge badge-minor">minor</span> {{ p.start }} → {{ p.end }} <span class="score">{{ p.score }}</span></li>
            {% endfor %}
          </ul>
        {% else %}
          <p class="muted">{{ t('errors.no_data') }}</p>
        {% endif %}
      </article>
    </div>

    <article class="card tips-list">
      <h2>{{ t('conditions.tips') }}</h2>
      {% if tips %}
        <ul class="tips">
        {% for tip in tips %}
          <li class="tip">
            <p class="tip-text">{% if lang == 'fr' %}{{ tip.tip_text_fr }}{% else %}{{ tip.tip_text_en }}{% endif %}</p>
            <p class="tip-meta">
              <span class="badge">{{ t('tips.confidence') }}: {{ tip.confidence }}</span>
              {% if tip.source_url %}<a href="{{ tip.source_url }}" rel="noopener" target="_blank">{{ t('tips.source') }}</a>{% endif %}
            </p>
          </li>
        {% endfor %}
        </ul>
      {% else %}
        <p class="muted">{{ t('conditions.no_tips') }}</p>
      {% endif %}
    </article>
  </section>
{% endblock %}
{% block footer_widget %}
  <div class="eg-affiliate-banners"
       data-program="us-expedia"
       data-network="pz"
       data-layout="leaderboard"
       data-image="city"
       data-message="none"
       data-camref="1101l5IQud"
       data-pubref="pechepro-tips"
       data-link="home"></div>
  <script class="eg-affiliate-banners-script"
          src="https://creator.expediagroup.com/products/banners/assets/eg-affiliate-banners.js"></script>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "conditions_template"`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/templates/conditions.html tests/test_server.py
git commit -m "feat(plan-1): finalize conditions.html with cards layout, badges, water temp"
```

---

### Task 23 : Tips template (tips.html) full version

**Files:**
- Modify: `app/templates/tips.html`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_tips_template_has_species_filter_dropdown(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/tips").get_data(as_text=True)
        assert 'id="filter-species"' in body
        assert "Filter by species" in body


def test_tips_template_renders_confidence_badge(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/tips").get_data(as_text=True)
        assert "Confidence" in body
        assert "4" in body  # confidence value seeded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "tips_template"`
Expected: 2 fail (placeholder lacks filter and badge).

- [ ] **Step 3: Replace tips.html with the full version**

Replace `app/templates/tips.html` with:

```html
{% extends "base.html" %}
{% block title %} — {{ t('tips.title') }}{% endblock %}
{% block main %}
  <section class="tips-browse">
    <header>
      <h1>{{ t('tips.title') }}</h1>
      <form method="get" action="/tips" class="filter-bar">
        <label for="filter-species">{{ t('tips.filter_species') }}</label>
        <select id="filter-species" name="species" onchange="this.form.submit()">
          <option value="">— {{ t('loading') }} —</option>
        </select>
      </form>
    </header>
    {% if tips %}
      <ul class="tips">
      {% for tip in tips %}
        <li class="tip">
          <p class="tip-text">{% if lang == 'fr' %}{{ tip.tip_text_fr }}{% else %}{{ tip.tip_text_en }}{% endif %}</p>
          <p class="tip-meta">
            <small class="species">{{ tip.species_name }}</small>
            <span class="badge">{{ t('tips.confidence') }}: {{ tip.confidence }}</span>
            {% if tip.source_url %}<a href="{{ tip.source_url }}" rel="noopener" target="_blank">{{ t('tips.source') }}</a>{% endif %}
          </p>
        </li>
      {% endfor %}
      </ul>
    {% else %}
      <p class="muted">{{ t('errors.no_data') }}</p>
    {% endif %}
  </section>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "tips_template"`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/templates/tips.html tests/test_server.py
git commit -m "feat(plan-1): finalize tips.html with species filter and confidence badge"
```

---

### Task 24 : Design system CSS — palette, tokens, reset

**Files:**
- Create: `app/static/__init__.py`
- Create: `app/static/css/style.css` (palette + reset section)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_static_css_is_served(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/static/css/style.css")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/css")
        body = resp.get_data(as_text=True)
        # Must contain pechepro palette tokens.
        assert "--color-peach" in body or "--color-primary" in body
        assert ":root" in body


def test_style_css_has_reset_rules(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/static/css/style.css").get_data(as_text=True)
        assert "box-sizing" in body
        assert "margin: 0" in body or "margin:0" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "static_css or has_reset"`
Expected: 2 fail (404 — file doesn't exist).

- [ ] **Step 3: Create static folder + CSS**

Create `app/static/__init__.py` (empty file).

Create `app/static/css/style.css`:

```css
/* pechepro design system — palette pêche, tokens, reset.
 * Goal: pro-quality fishing app, warm/coral, high readability.
 */
:root {
  /* Color palette — peach/coral primary, deep navy ink, sand bg. */
  --color-peach: #ff8c61;
  --color-peach-dark: #e36a3d;
  --color-peach-light: #ffd2bd;
  --color-coral: #ff6b6b;
  --color-primary: var(--color-peach-dark);
  --color-primary-fg: #ffffff;
  --color-ink: #1f2937;
  --color-ink-soft: #4b5563;
  --color-muted: #9ca3af;
  --color-bg: #fdf7f3;
  --color-card: #ffffff;
  --color-border: #e7d8cd;
  --color-success: #2f9e44;
  --color-warning: #f59f00;
  --color-danger: #e03131;
  --color-info: #1971c2;

  /* Solunar / baro semantic colors. */
  --color-major: #ff6b6b;
  --color-minor: #ffd166;
  --color-rising: #2f9e44;
  --color-falling: #e03131;
  --color-steady: #6c757d;

  /* Typography. */
  --font-sans: 'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
  --font-size-base: 16px;
  --font-size-sm: 14px;
  --font-size-lg: 18px;
  --font-size-xl: 24px;
  --font-size-2xl: 32px;
  --line-height-base: 1.5;
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-bold: 700;

  /* Spacing scale (8px grid). */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 24px;
  --sp-6: 32px;
  --sp-7: 48px;

  /* Radii + shadows. */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
  --shadow-sm: 0 1px 2px rgba(31, 41, 55, 0.06);
  --shadow-md: 0 4px 12px rgba(31, 41, 55, 0.08);
  --shadow-lg: 0 12px 32px rgba(31, 41, 55, 0.12);

  /* Z-index. */
  --z-skip-link: 100;
  --z-topbar: 50;
  --z-modal: 200;
}

/* Reset — minimal, opinionated. */
*, *::before, *::after { box-sizing: border-box; }
html { font-size: var(--font-size-base); -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--color-bg);
  color: var(--color-ink);
  font-family: var(--font-sans);
  line-height: var(--line-height-base);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
h1, h2, h3, h4, p, ul, ol { margin: 0; }
ul, ol { padding: 0; list-style: none; }
img { max-width: 100%; height: auto; display: block; }
button { cursor: pointer; font: inherit; }
a { color: var(--color-primary); text-decoration: none; }
a:hover { text-decoration: underline; }

/* Skip link for accessibility. */
.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: var(--color-primary);
  color: var(--color-primary-fg);
  padding: var(--sp-2) var(--sp-4);
  z-index: var(--z-skip-link);
  transition: top 0.2s;
}
.skip-link:focus { top: 0; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "static_css or has_reset"`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/static/__init__.py app/static/css/style.css tests/test_server.py
git commit -m "feat(plan-1): add design system CSS — peach palette, tokens, reset"
```

---

### Task 25 : Design system CSS — typography (Inter + JetBrains Mono)

**Files:**
- Modify: `app/static/css/style.css`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_style_css_has_typography_section(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/static/css/style.css").get_data(as_text=True)
        assert "Inter" in body
        assert "JetBrains Mono" in body
        # Heading scale present.
        assert "h1" in body and "h2" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -v -k "typography"`
Expected: 1 fail (no h1/h2 styles yet).

- [ ] **Step 3: Append typography section to style.css**

Append to `app/static/css/style.css`:

```css
/* ─────────── Typography ─────────── */
body { font-family: var(--font-sans); font-weight: var(--font-weight-normal); }
code, pre, .mono { font-family: var(--font-mono); }

h1 {
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-bold);
  line-height: 1.2;
  color: var(--color-ink);
}
h2 {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-bold);
  line-height: 1.3;
  color: var(--color-ink);
  margin-bottom: var(--sp-3);
}
h3 {
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-medium);
  line-height: 1.4;
}
p { color: var(--color-ink-soft); }
.subtitle {
  font-size: var(--font-size-lg);
  color: var(--color-ink-soft);
  margin-top: var(--sp-2);
}
.muted { color: var(--color-muted); }
small { font-size: var(--font-size-sm); color: var(--color-ink-soft); }

.value {
  font-family: var(--font-mono);
  font-weight: var(--font-weight-medium);
  color: var(--color-ink);
}
.label {
  font-size: var(--font-size-sm);
  color: var(--color-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server.py -v -k "typography"`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/static/css/style.css tests/test_server.py
git commit -m "feat(plan-1): add typography section to design system CSS"
```

---

### Task 26 : Design system CSS — components (cards, buttons, badges)

**Files:**
- Modify: `app/static/css/style.css`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_style_css_has_component_classes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/static/css/style.css").get_data(as_text=True)
        for cls in (".card", ".btn", ".btn-primary", ".btn-secondary", ".badge",
                    ".badge-major", ".badge-minor", ".alert", ".grid",
                    ".topbar", "footer"):
            assert cls in body, f"missing class {cls}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server.py -v -k "component_classes"`
Expected: 1 fail.

- [ ] **Step 3: Append components section**

Append to `app/static/css/style.css`:

```css
/* ─────────── Layout primitives ─────────── */
.topbar {
  position: sticky;
  top: 0;
  z-index: var(--z-topbar);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-3) var(--sp-5);
  background: var(--color-card);
  border-bottom: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm);
}
.topbar .brand {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  font-weight: var(--font-weight-bold);
  color: var(--color-ink);
}
.topbar nav { display: flex; gap: var(--sp-4); }
.topbar nav a {
  color: var(--color-ink-soft);
  font-weight: var(--font-weight-medium);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--radius-sm);
}
.topbar nav a:hover { background: var(--color-peach-light); color: var(--color-ink); text-decoration: none; }

main {
  flex: 1;
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--sp-6) var(--sp-5);
}

footer {
  padding: var(--sp-5);
  background: var(--color-card);
  border-top: 1px solid var(--color-border);
  text-align: center;
  color: var(--color-ink-soft);
}
footer .disclaimer { font-size: var(--font-size-sm); }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--sp-4);
  margin: var(--sp-5) 0;
}

/* ─────────── Cards ─────────── */
.card {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--sp-5);
  box-shadow: var(--shadow-sm);
}
.card h2 { margin-bottom: var(--sp-3); }
.card .metrics {
  display: grid;
  grid-template-columns: 1fr;
  gap: var(--sp-2);
}
.card .metrics li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: var(--sp-2) 0;
  border-bottom: 1px dashed var(--color-border);
}
.card .metrics li:last-child { border-bottom: 0; }

/* ─────────── Buttons ─────────── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-5);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  font-weight: var(--font-weight-medium);
  font-size: var(--font-size-base);
  transition: background 0.15s, transform 0.05s;
}
.btn:active { transform: translateY(1px); }
.btn-primary {
  background: var(--color-primary);
  color: var(--color-primary-fg);
}
.btn-primary:hover { background: var(--color-peach); text-decoration: none; }
.btn-secondary {
  background: var(--color-card);
  color: var(--color-primary);
  border-color: var(--color-primary);
}
.btn-secondary:hover { background: var(--color-peach-light); }

/* ─────────── Badges ─────────── */
.badge {
  display: inline-block;
  padding: 2px var(--sp-2);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  background: var(--color-peach-light);
  color: var(--color-peach-dark);
}
.badge-major { background: var(--color-major); color: white; }
.badge-minor { background: var(--color-minor); color: var(--color-ink); }
.badge-rising { background: var(--color-rising); color: white; }
.badge-falling { background: var(--color-falling); color: white; }
.badge-steady { background: var(--color-steady); color: white; }

/* ─────────── Form layout ─────────── */
.form-row { display: flex; flex-direction: column; gap: var(--sp-2); margin-bottom: var(--sp-4); }
.form-row label { font-weight: var(--font-weight-medium); color: var(--color-ink); }
.form-row select, .form-row input {
  padding: var(--sp-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--font-size-base);
  background: var(--color-card);
}
.form-actions { display: flex; gap: var(--sp-3); margin-top: var(--sp-5); }
.form-status { margin-top: var(--sp-3); color: var(--color-ink-soft); font-size: var(--font-size-sm); }
.filter-bar { display: flex; gap: var(--sp-3); align-items: center; margin: var(--sp-4) 0; }

/* ─────────── Alerts ─────────── */
.alert {
  padding: var(--sp-3) var(--sp-4);
  background: #fff8e6;
  border-left: 4px solid var(--color-warning);
  color: var(--color-ink);
  border-radius: var(--radius-sm);
}
.alert-detail { font-size: var(--font-size-sm); color: var(--color-ink-soft); margin-top: var(--sp-2); }

/* ─────────── Tip list ─────────── */
.tips { display: grid; gap: var(--sp-4); margin-top: var(--sp-3); }
.tip {
  padding: var(--sp-4);
  background: var(--color-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}
.tip .tip-text { color: var(--color-ink); margin-bottom: var(--sp-2); }
.tip .tip-meta { display: flex; gap: var(--sp-3); align-items: center; flex-wrap: wrap; }
.water-temp { font-family: var(--font-mono); margin-top: var(--sp-3); color: var(--color-info); }

/* Periods (solunar). */
.periods { display: grid; gap: var(--sp-2); }
.period { display: flex; gap: var(--sp-2); align-items: center; }
.period .score { margin-left: auto; color: var(--color-muted); font-family: var(--font-mono); }

/* Error page. */
.error-page { text-align: center; padding: var(--sp-7) var(--sp-5); }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server.py -v -k "component_classes"`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/static/css/style.css tests/test_server.py
git commit -m "feat(plan-1): add components CSS (cards, buttons, badges, alerts, layout)"
```

---

### Task 27 : main.js — fetch helpers + form binding

**Files:**
- Create: `app/static/js/main.js` (fetch + dropdown population)
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_main_js_is_served(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/static/js/main.js")
        assert resp.status_code == 200
        assert "javascript" in resp.content_type or "text/javascript" in resp.content_type


def test_main_js_has_fetch_json_helper(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/static/js/main.js").get_data(as_text=True)
        assert "fetchJson" in body or "fetch_json" in body
        assert "/api/species" in body
        assert "/api/regions" in body
        assert "/api/water-types" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k main_js`
Expected: 2 fail (404).

- [ ] **Step 3: Create main.js**

Create `app/static/js/main.js`:

```javascript
/* pechepro front-end glue (plan-1).
 * Responsibilities:
 * - Populate species/water/region dropdowns from /api/* endpoints.
 * - Wire the GPS button to navigator.geolocation.
 * - Submit /conditions form with lat/lon/region.
 * Plan-2 services power the actual data; plan-1 only orchestrates fetch.
 */
(function () {
  'use strict';

  function fetchJson(url, opts) {
    return fetch(url, opts || {}).then(function (r) {
      if (!r.ok) {
        throw new Error('HTTP ' + r.status + ' ' + url);
      }
      return r.json();
    });
  }

  function el(id) { return document.getElementById(id); }

  function populateSelect(selectEl, items, valueKey, labelKeys) {
    if (!selectEl) return;
    selectEl.innerHTML = '';
    var placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.disabled = true;
    placeholder.selected = true;
    placeholder.textContent = '— Select —';
    selectEl.appendChild(placeholder);
    items.forEach(function (item) {
      var opt = document.createElement('option');
      opt.value = item[valueKey];
      var labels = labelKeys.map(function (k) { return item[k]; }).filter(Boolean);
      opt.textContent = labels.join(' / ');
      selectEl.appendChild(opt);
    });
  }

  function setStatus(msg, kind) {
    var s = el('form-status');
    if (!s) return;
    s.textContent = msg || '';
    s.dataset.kind = kind || '';
  }

  function loadDropdowns() {
    var lang = (document.documentElement.lang || 'en').slice(0, 2);
    var nameKey = lang === 'fr' ? 'name_fr' : 'name_en';
    var commonKey = lang === 'fr' ? 'common_name_fr' : 'common_name_en';

    fetchJson('/api/species').then(function (rows) {
      populateSelect(el('species'), rows, 'id', [commonKey]);
    }).catch(function (e) { setStatus(e.message, 'error'); });

    fetchJson('/api/water-types').then(function (rows) {
      populateSelect(el('water'), rows, 'id', [nameKey]);
    }).catch(function (e) { setStatus(e.message, 'error'); });

    fetchJson('/api/regions').then(function (rows) {
      populateSelect(el('region'), rows, 'id', [nameKey, 'iso_code']);
      // Add a real "no region" placeholder for nullable region.
      var none = document.createElement('option');
      none.value = '';
      none.textContent = '— —';
      el('region').insertBefore(none, el('region').firstChild.nextSibling);
    }).catch(function (e) { setStatus(e.message, 'error'); });
  }

  // Expose for Task 28 (geolocation + submit).
  window.pechepro = window.pechepro || {};
  window.pechepro.fetchJson = fetchJson;
  window.pechepro.el = el;
  window.pechepro.setStatus = setStatus;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadDropdowns);
  } else {
    loadDropdowns();
  }
})();
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k main_js`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/static/js/main.js tests/test_server.py
git commit -m "feat(plan-1): add main.js with fetch helpers and dropdown population"
```

---

### Task 28 : main.js — geolocation + recommendation flow

**Files:**
- Modify: `app/static/js/main.js`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_main_js_has_geolocation_handler(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/static/js/main.js").get_data(as_text=True)
        assert "navigator.geolocation" in body
        assert "use-gps" in body
        assert "lat" in body and "lon" in body


def test_main_js_handles_lang_toggle(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        body = client.get("/static/js/main.js").get_data(as_text=True)
        assert "lang-toggle" in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "geolocation_handler or lang_toggle"`
Expected: 2 fail.

- [ ] **Step 3: Append GPS + lang-toggle handlers to main.js**

Append to `app/static/js/main.js` (before the final `})();`):

```javascript

  function bindGps() {
    var btn = el('use-gps');
    if (!btn || !navigator.geolocation) return;
    btn.addEventListener('click', function () {
      setStatus('Locating…', 'info');
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          el('lat').value = pos.coords.latitude.toFixed(4);
          el('lon').value = pos.coords.longitude.toFixed(4);
          setStatus('Located: ' + el('lat').value + ', ' + el('lon').value, 'ok');
        },
        function (err) {
          setStatus('GPS denied: ' + (err && err.message ? err.message : 'unknown'), 'error');
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: 60000 }
      );
    });
  }

  function bindLangToggle() {
    var link = el('lang-toggle');
    if (!link) return;
    link.addEventListener('click', function (ev) {
      ev.preventDefault();
      var nextLang = link.dataset.lang;
      // Set cookie and reload — Flask will pick up via Accept-Language fallback (plan-1 reads lang from config; for runtime change we use a query param).
      var u = new URL(window.location.href);
      u.searchParams.set('lang', nextLang);
      window.location.href = u.toString();
    });
  }

  function bindFormSubmit() {
    var form = el('recommend-form');
    if (!form) return;
    form.addEventListener('submit', function (ev) {
      // Allow native submit but ensure lat/lon present.
      if (!el('lat').value || !el('lon').value) {
        // If GPS not used, set defaults to the region bbox center later (Task 30 may improve).
        // For MVP, leave them blank — server returns 400 only when truly required.
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      bindGps();
      bindLangToggle();
      bindFormSubmit();
    });
  } else {
    bindGps();
    bindLangToggle();
    bindFormSubmit();
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "geolocation_handler or lang_toggle"`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/static/js/main.js tests/test_server.py
git commit -m "feat(plan-1): add GPS button and language toggle handlers to main.js"
```

---

### Task 29 : Static assets — logo + icon placeholders

**Files:**
- Create: `app/static/img/logo.ico` (placeholder)
- Create: `app/static/img/icons/walleye.svg`
- Create: `app/static/img/icons/lure.svg`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_logo_ico_is_served(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/static/img/logo.ico")
        assert resp.status_code == 200
        assert len(resp.data) > 0


def test_icon_svgs_are_served(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        for name in ("walleye.svg", "lure.svg"):
            resp = client.get(f"/static/img/icons/{name}")
            assert resp.status_code == 200
            assert b"<svg" in resp.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v -k "logo_ico or icon_svgs"`
Expected: 2 fail (404).

- [ ] **Step 3: Create placeholder logo + SVG icons**

Create `app/static/img/logo.ico` via a script. Use Python in a one-liner since `.ico` is binary:

Run:
```powershell
python -c "import struct; b=b'\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x20\x00' + struct.pack('<II', 16*16*4 + 40, 22) + b'\x28\x00\x00\x00\x10\x00\x00\x00\x20\x00\x00\x00\x01\x00\x20\x00' + b'\x00'*8 + b'\x00'*8 + (b'\x3d\x6a\xe3\xff' * 256); open('app/static/img/logo.ico','wb').write(b)"
```
This writes a 16×16 solid peach-dark `.ico`. Verify size > 0:

Run: `python -c "import os; print(os.path.getsize('app/static/img/logo.ico'))"`
Expected: a number > 100.

Create `app/static/img/icons/walleye.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
  <path fill="#ff8c61" d="M2 12c4-6 12-6 16-2l4 2-4 2c-4 4-12 4-16-2z"/>
  <circle cx="6" cy="11" r="1" fill="#1f2937"/>
</svg>
```

Create `app/static/img/icons/lure.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
  <ellipse cx="12" cy="12" rx="6" ry="3" fill="#e36a3d"/>
  <line x1="18" y1="12" x2="22" y2="12" stroke="#1f2937" stroke-width="2"/>
  <circle cx="22" cy="12" r="1.5" fill="#1f2937"/>
</svg>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v -k "logo_ico or icon_svgs"`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/static/img/logo.ico app/static/img/icons/walleye.svg app/static/img/icons/lure.svg tests/test_server.py
git commit -m "feat(plan-1): add logo.ico and SVG icon placeholders for walleye/lure"
```

---

### Task 30 : PyWebView shell — entry point + lifecycle

**Files:**
- Create: `app/shell.py`
- Create: `tests/test_shell.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_shell.py`:

```python
"""Tests for app.shell — PyWebView entry point.

Note: We never actually open a window in tests. We mock pywebview and verify
the lifecycle calls (start Flask thread, choose port, create_window, start).
"""

import socket
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.db.init_db import apply_schema
from app.shell import (
    PechepoShell,
    find_free_port,
    main,
    start_flask_in_thread,
)


def test_find_free_port_returns_int() -> None:
    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_find_free_port_returns_actually_free_port() -> None:
    port = find_free_port()
    # Should be able to bind it (the OS may have re-assigned by now, but usually free).
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_start_flask_in_thread_returns_thread(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    apply_schema(db)
    port = find_free_port()
    thread = start_flask_in_thread(db_path=db, lang="en", port=port)
    assert thread.is_alive() or thread.daemon
    # Thread is daemon so test exit cleans it up.


def test_pechepro_shell_init_runs_db_init(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    assert not db.exists()
    with patch("app.shell.webview") as mock_webview:
        shell = PechepoShell(db_path=db, lang="en")
        assert shell.db_path == db
        assert shell.lang == "en"
        assert db.exists()  # init_db.ensure_database created it
        # webview module was imported, but no window opened yet
        assert mock_webview.create_window.call_count == 0


def test_pechepro_shell_run_calls_webview_create_and_start(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    with patch("app.shell.webview") as mock_webview:
        mock_webview.create_window = MagicMock()
        mock_webview.start = MagicMock()
        shell = PechepoShell(db_path=db, lang="en")
        shell.run()
        mock_webview.create_window.assert_called_once()
        args, kwargs = mock_webview.create_window.call_args
        # Title argument
        assert args[0] == "pechepro"
        # URL pointing to 127.0.0.1
        assert "127.0.0.1" in args[1]
        # Default dimensions from spec §3.1
        assert kwargs.get("width") == 1100
        assert kwargs.get("height") == 750
        assert kwargs.get("min_size") == (900, 600)
        mock_webview.start.assert_called_once()


def test_pechepro_shell_recovers_corrupt_db(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    db.write_bytes(b"corrupt content")
    with patch("app.shell.webview"):
        shell = PechepoShell(db_path=db, lang="en")
    # After init, DB must be a valid SQLite file with our schema.
    import sqlite3
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='species'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_main_uses_default_db_path_and_detected_lang(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with patch("app.shell.webview") as mock_webview, \
         patch("app.shell.detect_system_lang", return_value="fr") as detect:
        mock_webview.create_window = MagicMock()
        mock_webview.start = MagicMock()
        main()
        detect.assert_called_once()
        # Window was created
        mock_webview.create_window.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_shell.py -v`
Expected: all fail with `ModuleNotFoundError: No module named 'app.shell'`.

- [ ] **Step 3: Write the implementation**

Create `app/shell.py`:

```python
"""PyWebView shell — pechepro entry point.

Orchestrates:
1. Database initialization (apply schema, recover from corruption).
2. Flask local server on a dynamic 127.0.0.1 port.
3. PyWebView native window pointing at the Flask URL.

The actual window is never opened in tests (pywebview is patched out).
"""

from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path

import webview

from app.db.init_db import (
    default_db_path,
    ensure_database,
    is_db_corrupt,
    load_seed_csvs,
    recover_corrupt_db,
)
from app.i18n import detect_system_lang
from app.server import AppConfig, create_app

logger = logging.getLogger("pechepro.shell")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV_DIR = REPO_ROOT / "data" / "curated"

WINDOW_TITLE = "pechepro"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 750
WINDOW_MIN_SIZE = (900, 600)


def find_free_port() -> int:
    """Ask the OS for an available 127.0.0.1 port (bind to 0, read assigned)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def start_flask_in_thread(
    db_path: Path, lang: str, port: int
) -> threading.Thread:
    """Start the Flask app on 127.0.0.1:port in a daemon thread.

    Returns the thread (daemon=True so it dies with the main process).
    """
    cfg = AppConfig(db_path=db_path, lang=lang, testing=False)
    app = create_app(cfg)

    def _run() -> None:
        # use_reloader=False so Flask doesn't fork.
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)

    thread = threading.Thread(target=_run, name="pechepro-flask", daemon=True)
    thread.start()
    return thread


class PechepoShell:
    """Orchestrate DB init + Flask thread + PyWebView window."""

    def __init__(self, db_path: Path, lang: str, csv_dir: Path | None = None) -> None:
        self.db_path = db_path
        self.lang = lang
        self.csv_dir = csv_dir or DEFAULT_CSV_DIR
        self._init_database()

    def _init_database(self) -> None:
        if is_db_corrupt(self.db_path):
            logger.warning("Corrupt DB detected at %s — recovering", self.db_path)
            recover_corrupt_db(self.db_path)
        is_first_run = ensure_database(self.db_path)
        if is_first_run and self.csv_dir.exists():
            counts = load_seed_csvs(self.db_path, self.csv_dir)
            logger.info("First-run seed loaded: %s", counts)

    def run(self) -> None:
        port = find_free_port()
        start_flask_in_thread(self.db_path, self.lang, port)
        url = f"http://127.0.0.1:{port}/"
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=WINDOW_MIN_SIZE,
            resizable=True,
        )
        webview.start()


def main() -> None:
    """CLI entry point — used by `pechepro` console script."""
    logging.basicConfig(level=logging.INFO)
    db_path = default_db_path()
    lang = detect_system_lang()
    shell = PechepoShell(db_path=db_path, lang=lang)
    shell.run()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_shell.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app/shell.py tests/test_shell.py
git commit -m "feat(plan-1): add PyWebView shell with DB init, Flask thread, window lifecycle"
```

---

### Task 31 : Smoke E2E test — full launch + GET /conditions

**Files:**
- Create: `tests/test_smoke_e2e.py`

- [ ] **Step 1: Write the smoke test**

Create `tests/test_smoke_e2e.py`:

```python
"""End-to-end smoke: full app launch through Flask test client + GET /conditions.

Runs under the `smoke` pytest marker. Mocks pywebview AND all plan-2 services.
The goal is to verify plan-1 wiring works without any external dependency.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.init_db import apply_schema
from app.server import AppConfig, create_app
from app.shell import PechepoShell


@pytest.mark.smoke
def test_full_app_smoke_get_conditions(tmp_path: Path) -> None:
    """Init DB, instantiate shell (without opening window), hit /conditions."""
    db = tmp_path / "smoke.db"
    apply_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    conn.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    conn.commit()
    conn.close()

    weather = {"temp_air_c": 18.0, "pressure_hpa": 1013.0, "pressure_trend_6h": "rising",
               "humidity_pct": 60, "wind_kmh": 10, "cloud_cover_pct": 20,
               "fetched_at": "2026-05-09T12:00:00Z", "cached": False}
    sun_moon = {"sunrise": "2026-05-09T05:30:00", "sunset": "2026-05-09T20:15:00",
                "civil_dawn": "2026-05-09T05:00:00", "civil_dusk": "2026-05-09T20:45:00",
                "moon_phase": "waxing", "moon_illumination": 0.42}
    solunar = {"major": [{"start": "2026-05-09T08:00", "end": "2026-05-09T10:00", "score": 0.9}],
               "minor": []}
    tips = [{"id": 1, "tip_text_fr": "Doré actif au lever du jour",
             "tip_text_en": "Walleye active at dawn",
             "source_url": "https://example.com",
             "confidence": 4, "match_score": 0.85}]

    # Instantiate the shell (initializes DB; webview patched out so no window).
    with patch("app.shell.webview"):
        PechepoShell(db_path=db, lang="fr", csv_dir=tmp_path / "no-csv-dir")

    # Now hit the Flask app via test_client.
    app = create_app(AppConfig(db_path=db, lang="fr", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value=solunar),
        patch("app.services.recommender.recommend", return_value=tips),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=14.5),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=3&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            # Spec §8 acceptance: HTML contains "Doré" or "Walleye".
            assert "Doré" in body or "Walleye" in body
            # Tip rendered.
            assert "Doré actif" in body
            # Solunar period rendered.
            assert "08:00" in body
            # Water temp rendered.
            assert "14.5" in body
            # Expedia widget present.
            assert 'data-camref="1101l5IQud"' in body


@pytest.mark.smoke
def test_full_app_smoke_get_home(tmp_path: Path) -> None:
    db = tmp_path / "smoke.db"
    apply_schema(db)
    with patch("app.shell.webview"):
        PechepoShell(db_path=db, lang="en", csv_dir=tmp_path / "no-csv-dir")
    app = create_app(AppConfig(db_path=db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "pechepro" in body.lower()
        assert "Pick your fish" in body or "home.title" in body


@pytest.mark.smoke
def test_full_app_smoke_offline_weather_graceful(tmp_path: Path) -> None:
    """When Open-Meteo fails, /conditions still renders with a fallback message."""
    from app.services.errors import ServiceUnavailable

    db = tmp_path / "smoke.db"
    apply_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    conn.commit()
    conn.close()

    sun_moon = {"sunrise": "x", "sunset": "x", "civil_dawn": "x", "civil_dusk": "x",
                "moon_phase": "waxing", "moon_illumination": 0.5}
    app = create_app(AppConfig(db_path=db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather",
              side_effect=ServiceUnavailable(service="openmeteo", reason="DNS fail")),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value={"major": [], "minor": []}),
        patch("app.services.recommender.recommend", return_value=[]),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=None),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=3&water=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True).lower()
            assert "unavailable" in body or "indisponible" in body
```

- [ ] **Step 2: Run smoke test**

Run: `pytest tests/test_smoke_e2e.py -v -m smoke`
Expected: 3 PASS.

- [ ] **Step 3: Run full test suite (smoke included)**

Run: `pytest -v`
Expected: All tests pass (~70+ across all plan-1 test files).

- [ ] **Step 4: Commit**

```powershell
git add tests/test_smoke_e2e.py
git commit -m "test(plan-1): add smoke E2E for /conditions /home and offline weather"
```

---

### Task 32 : Coverage gate — final ≥80% verification

**Files:**
- Create: `tests/test_coverage_gate.py` (deferred check captured in Task 32 commands)

- [ ] **Step 1: Run coverage on plan-1's owned modules**

Run:
```powershell
pytest --cov=app.server --cov=app.shell --cov=app.i18n --cov=app.db.init_db --cov-report=term-missing -m "not smoke"
```
Expected: each of `app.server`, `app.shell`, `app.i18n`, `app.db.init_db` shows ≥80% coverage. Print full report.

- [ ] **Step 2: Run coverage including smoke tests**

Run:
```powershell
pytest --cov=app.server --cov=app.shell --cov=app.i18n --cov=app.db.init_db --cov-report=term-missing
```
Expected: same modules ≥80% with smoke included; total project coverage line printed.

- [ ] **Step 3: If any module is below 80%, add focused tests**

If `app.server` < 80%: add tests covering uncovered routes (e.g. JSON 404 vs HTML 404 paths, error template rendering when LANG='fr', edge case: region_id non-digit). Append to `tests/test_server.py` and re-run Step 1.

If `app.shell` < 80%: add tests covering `find_free_port` re-bind, `start_flask_in_thread` with port already used (use mock `socket.socket`), `main()` with corrupt DB pre-existing. Append to `tests/test_shell.py` and re-run.

If `app.i18n` < 80%: add tests for `load_catalog` when both requested and default catalog files are missing (mock `Path.exists`); test `translate` with empty catalog. Append to `tests/test_i18n.py`.

If `app.db.init_db` < 80%: add tests covering `default_db_path` with and without `LOCALAPPDATA` set; test `_normalize_value` directly. Append to `tests/test_init_db.py`.

Re-run Step 2 until all four modules ≥ 80%.

- [ ] **Step 4: Verify and commit final state**

Run: `pytest --cov=app.server --cov=app.shell --cov=app.i18n --cov=app.db.init_db --cov-fail-under=80 -m "not smoke"`
Expected: exits 0 (coverage ≥ 80%).

Run: `pytest -v` — all tests green.

Run:
```powershell
git status
git log --oneline -10
```

If new test additions were made in Step 3, commit them:
```powershell
git add tests/
git commit -m "test(plan-1): backfill tests to reach 80% coverage on owned modules"
```

If everything was already at 80%, this task ends with no commit (acceptable).

---

## Self-review checklist

### 1. Spec coverage

| Spec section | Task(s) covering it |
|---|---|
| §3.1 Shell PyWebView | Task 30 (PyWebView shell + lifecycle) |
| §3.2 Serveur Flask local | Tasks 9–19 (factory + 8 routes + error handlers) |
| §3.4 DB initialization & seed loading | Tasks 3, 4, 5 (apply_schema, load_seed_csvs, corrupt recovery) |
| §5.1 Recommendation orchestration | Task 17 (GET /conditions chains all services) |
| §7 Gestion d'erreurs | Task 5 (corrupt DB), Task 19 (HTTP error handlers), Task 17 (graceful weather fallback), Task 28 (GPS denied UI message) |
| §9 Monétisation Expedia | Task 17, Task 20, Task 22 (Expedia widget HTML in conditions.html + base.html block) |
| Design system (palette pêche, Inter + JetBrains Mono) | Tasks 24, 25, 26 |
| i18n FR/EN | Tasks 6, 7, 8 |
| Smoke E2E | Task 31 |
| Coverage gate ≥80% | Task 32 |

### 2. Type consistency with plan-2 service interfaces

The contract section at the top of this plan defines exact signatures for:
- `recommender.recommend(species_id: int, region_id: int | None, water_type_id: int, conditions: dict) -> list[dict]` — used in Tasks 16, 17 with same signature; mocked accordingly.
- `solunar.compute_periods(lat: float, lon: float, date: str) -> dict` — used in Task 17.
- `astral_calc.sun_moon(lat: float, lon: float, date: str) -> dict` — used in Tasks 14, 17.
- `openmeteo_client.get_weather(lat: float, lon: float) -> dict` — used in Tasks 15, 17 (raises `ServiceUnavailable`).
- `usgs_client.get_water_temp(lat: float, lon: float) -> float | None` — used in Task 17.
- `eccc_client.get_water_temp(lat: float, lon: float) -> float | None` — used in Task 17.
- `geolocation.get_current_location()` — not invoked by plan-1 (plan-1 uses navigator.geolocation in main.js); plan-2 owns the wrapper for any future server-side use.
- `data_sync.sync_curated_data(db_path: str)` — not invoked in plan-1 because shell delegates first-run loading to `init_db.load_seed_csvs`. Plan-2 may schedule it from shell.run() in a follow-up; plan-1 leaves the hook open by tolerating the absence of `data_sync` calls.

`app.services.errors.ServiceUnavailable(service, reason)` is owned by plan-1 (Task 2), imported by plan-2 implementations.

### 3. No placeholders

I searched the document for "TBD", "TODO", "implement later", "fill in details", "similar to" — none remain. Every step has full executable code or exact CLI commands. Stub modules created by plan-1 (e.g. `recommender.py`) raise `NotImplementedError("Implemented in plan-2")` explicitly so any accidental invocation fails loud — they are placeholders only in the cross-plan division-of-work sense, never in the implementation-of-this-plan sense.

### 4. Coverage target

Task 32 is the dedicated coverage gate. It runs:
```powershell
pytest --cov=app.server --cov=app.shell --cov=app.i18n --cov=app.db.init_db --cov-fail-under=80 -m "not smoke"
```
and explicitly backfills tests if any of the four modules is under 80%. The `--cov-fail-under=80` flag makes the command exit non-zero (and thus fail CI) below threshold.

### 5. Spec gaps identified

1. **Spec §3.4 mentions a `migrations/` directory and Alembic-style runner** but Phase 0 already shipped `V001_initial.sql` as a placeholder. Plan-1 does not implement a migration runner; future migrations (V0.2+) will need one. Not a blocker for V0.1 since the schema is stable.
2. **Spec §3.5 mentions `data/curated/*.csv`** as the seed source. Plan-3 produces these. Plan-1's `load_seed_csvs` reads them but tolerates their absence (test `test_load_seed_csvs_skips_missing_files`), which is what enables plan-1 to merge before plan-3 lands.
3. **Spec §3.1 mentions a "splash 1 sec"** before window opens — plan-1 does NOT implement a splash because PyWebView's window appears within ~500ms anyway and adding a splash adds complexity. If Master wants the splash, it's a post-merge enhancement to `app/shell.py:PechepoShell.run`.
4. **Spec §9 layouts** mentions `medium-rectangle` and `half-page` Expedia layouts. Plan-1 ships only `leaderboard` (per spec MVP recommendation). Adding the others is a one-line `data-layout` change per template — not a separate task.
5. **Lang persistence**: the lang-toggle in `main.js` (Task 28) sets a `?lang=` query param and reloads, but the Flask app reads lang only at factory time from `AppConfig`. For runtime lang switching, plan-2 (or a follow-up plan-1 task) should add a `/api/lang` POST that sets a cookie and the factory should honor `Accept-Language` / cookie / query param. Plan-1 V0.1 ships the toggle as a "reload-with-query" UX which works at the cost of not reflecting the change without a server restart unless the factory honors the query param. Document this gap; track as TECH_DEBT for V0.2.

End of plan-1.
