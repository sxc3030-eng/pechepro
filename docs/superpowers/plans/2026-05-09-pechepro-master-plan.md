# Pechepro Implementation Plan — Master Overview

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement the sub-plans task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build pechepro V0.1 — application Windows desktop standalone gratuite de pêche en Amérique du Nord avec recommandations personnalisées par espèce × région × conditions (météo, pression baro, lune, soleil, solunar). Distribuée en `.exe` + installer Inno Setup, monétisée via widget Expedia Affiliate Banners.

**Architecture:** Pure Python desktop app — PyWebView shell + Flask local (port dynamique 127.0.0.1) + SQLite locale (`%LOCALAPPDATA%\pechepro\pechepro.db`). Tous les services in-process. APIs externes (Open-Meteo, USGS, ECCC) appelées directement par l'app. Données curées bundlées dans le `.exe` au build + sync `1×/24h` depuis `raw.githubusercontent.com`. Zero backend, zero infra serveur. Voir [spec v3](../specs/2026-05-09-pechepro-design.md).

**Tech Stack:** Python 3.13 · PyWebView 5.x · Flask 3.x · SQLite (stdlib) · pytest + pytest-asyncio · httpx · astral · skyfield · winsdk · PyInstaller 6 · Inno Setup 6 · GitHub Actions (windows-latest)

---

## Spec coverage

| Spec section | Couvert par |
|---|---|
| §1 Problème et objectifs | Tous les plans (critères d'acceptation) |
| §2 Architecture | Tous les plans |
| §3.1 Shell PyWebView | plan-1 |
| §3.2 Serveur Flask local | plan-1 |
| §3.3 Services Python | plan-2 |
| §3.4 Base de données locale | **Phase 0** (schéma) + plan-3 (seed data) |
| §3.5 Données curées | plan-3 |
| §3.6 Build & distribution | plan-4 |
| §4 Schéma DB | **Phase 0** (DDL) |
| §5 Flux de données | plan-1 (orchestration) + plan-2 (logique) |
| §6 Espèces MVP | plan-3 |
| §7 Gestion d'erreurs | plan-1 + plan-2 |
| §8 Stratégie de tests | Tous les plans |
| §9 Monétisation (Expedia) | plan-1 (widget integration) |
| §10 Hors scope | Documenté, pas implémenté V0.1 |
| §11 Risques | plan-2 (rate-limit fallbacks) + plan-4 (SmartScreen) |
| §12 Décomposition | Ce master plan |
| §13 Done criteria | plan-4 (smoke 20 scénarios) |

## Sub-plans

| Plan | Path | Scope |
|---|---|---|
| 1 — App core | [plan-1-app-core.md](2026-05-09-pechepro-plan-1-app-core.md) | PyWebView shell, Flask local, routes/templates Home/Conditions/Tips, design system CSS, i18n FR/EN, widget Expedia |
| 2 — Services | [plan-2-services.md](2026-05-09-pechepro-plan-2-services.md) | recommender, solunar, baro_analyzer, astral_calc, openmeteo_client, usgs_client, eccc_client, data_sync, geolocation |
| 3 — Data curation | [plan-3-data-curation.md](2026-05-09-pechepro-plan-3-data-curation.md) | 8 CSVs : species (15), regions (65), water_types (5), lures (~30), color_visibility (~120), tips (≥300), solunar_rules, baro_rules |
| 4 — Build & deploy | [plan-4-build-deploy.md](2026-05-09-pechepro-plan-4-build-deploy.md) | PyInstaller spec, Inno Setup script, GitHub Actions release workflow, smoke checklist 20 scénarios |
| ⚠️ — Cross-plan amendments | [cross-plan-amendments.md](2026-05-09-pechepro-cross-plan-amendments.md) | **READ FIRST** — reconciles plan-1 ↔ plan-2 service signatures (date type, db parameter, sync vs async). Authoritative. |

## Dependencies graph

```
                  ┌─────────────────────┐
                  │  Phase 0 (this doc) │
                  │  Foundation         │
                  │  - pyproject.toml   │
                  │  - schema.sql       │
                  │  - pytest config    │
                  │  - app/ skeleton    │
                  └──────────┬──────────┘
                             │ unblocks
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌─────────┐    ┌─────────┐    ┌─────────┐
        │ plan-1  │    │ plan-2  │    │ plan-3  │
        │ app-core│    │ services│    │ data-cur│
        └────┬────┘    └────┬────┘    └────┬────┘
             │              │              │
             └──────────────┼──────────────┘
                            │ all merged to main
                            ▼
                      ┌─────────┐
                      │ plan-4  │
                      │ build   │
                      └─────────┘
```

**Phase 1** (plans 1, 2, 3) tournent **en parallèle** dans des worktrees séparés. **Phase 2** (plan 4) démarre une fois Phase 1 mergée sur `main`.

## Branching / worktree strategy

```powershell
cd D:\pechepro
git worktree add .claude\worktrees\plan-1-app-core      -b plan/app-core
git worktree add .claude\worktrees\plan-2-services      -b plan/services
git worktree add .claude\worktrees\plan-3-data-curation -b plan/data-curation
# Phase 2 (après merge des 3 ci-dessus) :
git worktree add .claude\worktrees\plan-4-build-deploy  -b plan/build-deploy
```

Chaque agent travaille dans son worktree, commits fréquemment, merge sur `main` (--no-ff) après code-review.

## Definition of done per phase

**Phase 0** (ce plan) — done quand :
- [ ] `pyproject.toml` existe, `pip install -e .[dev]` réussit
- [ ] `pytest` exécute proprement (0 tests collected acceptable au début)
- [ ] `app\db\schema.sql` existe avec les 8 tables du spec §4 + 3 tables runtime
- [ ] DDL valide : crée une SQLite vide en exécutant le schema, sans erreur
- [ ] `app\__init__.py` et `tests\__init__.py` existent
- [ ] Pre-commit configuré (ruff + black-style format + mypy)
- [ ] Workflow CI minimal (pytest sur push) green
- [ ] Tout committé sur `main`, tagué `phase-0-foundation`

**Phase 1** (plans 1+2+3) — done quand :
- [ ] Toutes les tasks de plan-1, plan-2, plan-3 cochées
- [ ] `pytest` montre ≥80% coverage sur `app\services\` et `app\db\`
- [ ] `pytest -m smoke` passe (smoke E2E : launch app + GET /conditions?species=3&water=1&lat=46.81&lon=-71.21 → HTML contient "Doré")
- [ ] Toutes les branches mergées sur `main`, tag `phase-1-implementation`

**Phase 2** (plan 4) — done quand :
- [ ] `dist\pechepro-setup.exe` build localement, taille <60 MB
- [ ] GitHub Actions workflow green sur un push de tag `v0.1.0-rc1`
- [ ] Smoke checklist 20 scénarios tous verts sur Windows clean
- [ ] Tag `v0.1.0` créé, GitHub release publiée avec asset `pechepro-setup.exe`

---

## Phase 0 — Foundation tasks (TDD strict)

Ces tasks sont **séquentielles** et **bloquent** Phase 1. Une seule personne (ou agent) les exécute. Estimation : ~45 min.

### Task 0.1 : Initialize Python project structure

**Files:**
- Create: `D:\pechepro\pyproject.toml`
- Create: `D:\pechepro\app\__init__.py`
- Create: `D:\pechepro\tests\__init__.py`
- Create: `D:\pechepro\tests\conftest.py`

- [ ] **Step 1: Create pyproject.toml with pinned deps**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "pechepro"
version = "0.1.0-dev"
description = "Application Windows standalone de pêche en Amérique du Nord"
readme = "README.md"
requires-python = ">=3.13"
license = { text = "Proprietary" }
authors = [{ name = "Master / sxc3030-eng" }]
keywords = ["fishing", "peche", "north-america", "desktop", "windows"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Operating System :: Microsoft :: Windows",
    "Programming Language :: Python :: 3.13",
]

dependencies = [
    "pywebview==5.4",
    "flask==3.0.3",
    "jinja2==3.1.4",
    "httpx==0.28.1",
    "astral==3.2",
    "skyfield==1.49",
    "winsdk==1.0.0b10; sys_platform == 'win32'",
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.4",
    "pytest-cov==6.0.0",
    "pytest-asyncio==0.24.0",
    "respx==0.21.1",
    "freezegun==1.5.1",
    "ruff==0.8.4",
    "mypy==1.13.0",
    "pre-commit==4.0.1",
]
build = [
    "pyinstaller==6.11.1",
]

[project.scripts]
pechepro = "app.shell:main"

[tool.setuptools.packages.find]
include = ["app*"]
exclude = ["tests*", "data*", "deploy*", "docs*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "--strict-markers -ra"
markers = [
    "smoke: end-to-end smoke tests (slow, requires network or full app launch)",
    "network: tests that require external network access",
]

[tool.coverage.run]
source = ["app"]
omit = ["app/shell.py"]
branch = true

[tool.coverage.report]
fail_under = 80
show_missing = true
exclude_lines = ["pragma: no cover", "if __name__ == .__main__.:"]

[tool.ruff]
line-length = 100
target-version = "py313"
extend-exclude = ["data", "deploy", "docs"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "B", "UP", "C90", "S", "RUF"]
ignore = ["S101"]  # assert usage in tests

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["S", "B011"]

[tool.mypy]
python_version = "3.13"
strict = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_unimported = true
exclude = ["tests/", "deploy/", "data/"]
```

- [ ] **Step 2: Create app/__init__.py**

```python
"""pechepro — Application Windows standalone de pêche Amérique du Nord."""

__version__ = "0.1.0-dev"
```

- [ ] **Step 3: Create tests/__init__.py**

```python
"""pechepro test suite."""
```

- [ ] **Step 4: Create tests/conftest.py**

```python
"""Shared pytest fixtures."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "app" / "db" / "schema.sql"


@pytest.fixture
def empty_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide a connection to a fresh in-memory SQLite database with schema applied."""
    db_path = tmp_path / "pechepro_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    yield conn
    conn.close()
```

- [ ] **Step 5: Verify install**

Run:
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```
Expected: install completes without error, `pip list` shows pytest 8.3.4 and pywebview 5.4.

- [ ] **Step 6: Verify pytest collects 0 tests cleanly**

Run: `pytest`
Expected output ends with: `no tests ran in X.XXs` (no errors).

- [ ] **Step 7: Commit**

```powershell
cd D:\pechepro
git add pyproject.toml app\__init__.py tests\__init__.py tests\conftest.py
git commit -m "chore(phase-0): init Python project structure with pinned deps"
```

---

### Task 0.2 : Create SQLite schema (DDL)

**Files:**
- Create: `D:\pechepro\app\db\__init__.py`
- Create: `D:\pechepro\app\db\schema.sql`
- Create: `D:\pechepro\tests\test_schema.py`

- [ ] **Step 1: Write the failing test**

Create `D:\pechepro\tests\test_schema.py`:

```python
"""Verify schema.sql is valid and creates the expected tables."""

import sqlite3

EXPECTED_TABLES = {
    "species",
    "regions",
    "water_types",
    "lures",
    "color_visibility",
    "tips",
    "solunar_rules",
    "baro_rules",
    "weather_cache",
    "user_prefs",
    "data_sync_meta",
}


def test_schema_creates_all_expected_tables(empty_db: sqlite3.Connection) -> None:
    rows = empty_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    actual = {row[0] for row in rows}
    missing = EXPECTED_TABLES - actual
    assert not missing, f"Missing tables: {missing}"


def test_schema_indexes_present(empty_db: sqlite3.Connection) -> None:
    rows = empty_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
    actual = {row[0] for row in rows}
    expected_indexes = {
        "idx_regions_iso",
        "idx_color_visibility_lookup",
        "idx_tips_species",
        "idx_tips_lookup",
    }
    missing = expected_indexes - actual
    assert not missing, f"Missing indexes: {missing}"


def test_species_constraints_country(empty_db: sqlite3.Connection) -> None:
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    empty_db.commit()
    # Bad country value should fail CHECK
    try:
        empty_db.execute(
            "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
            "VALUES (2, 'Test', 'Test', 'XX', 'TT')"
        )
        empty_db.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("Expected IntegrityError on country='XX'")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_schema.py -v`
Expected: 3 failures, all because `schema.sql` doesn't exist yet (FileNotFoundError in conftest).

- [ ] **Step 3: Create app/db/__init__.py**

```python
"""Database layer for pechepro."""
```

- [ ] **Step 4: Create app/db/schema.sql with full DDL from spec §4**

```sql
-- pechepro local SQLite schema (V0.1)
-- Generated from spec §4 — keep in sync.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS species (
    id INTEGER PRIMARY KEY,
    common_name_fr TEXT NOT NULL,
    common_name_en TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    family TEXT,
    typical_habitat TEXT,
    image_url TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    country TEXT NOT NULL CHECK(country IN ('CA','US','MX')),
    iso_code TEXT NOT NULL,
    bbox_lat_min REAL,
    bbox_lat_max REAL,
    bbox_lon_min REAL,
    bbox_lon_max REAL
);
CREATE INDEX IF NOT EXISTS idx_regions_iso ON regions(country, iso_code);

CREATE TABLE IF NOT EXISTS water_types (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lures (
    id INTEGER PRIMARY KEY,
    name_fr TEXT NOT NULL,
    name_en TEXT NOT NULL,
    category TEXT NOT NULL,
    image_url TEXT
);

CREATE TABLE IF NOT EXISTS color_visibility (
    id INTEGER PRIMARY KEY,
    water_clarity TEXT NOT NULL CHECK(water_clarity IN ('clear','stained','muddy')),
    light_level TEXT NOT NULL CHECK(light_level IN ('bright','overcast','dawn_dusk','night')),
    color TEXT NOT NULL,
    visibility_score INTEGER NOT NULL CHECK(visibility_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);
CREATE INDEX IF NOT EXISTS idx_color_visibility_lookup ON color_visibility(water_clarity, light_level);

CREATE TABLE IF NOT EXISTS tips (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    region_id INTEGER REFERENCES regions(id),
    water_type_id INTEGER REFERENCES water_types(id),
    season TEXT CHECK(season IN ('spring','summer','fall','winter','any')) DEFAULT 'any',
    baro_trend TEXT CHECK(baro_trend IN ('rising','falling','steady','any')) DEFAULT 'any',
    moon_phase TEXT CHECK(moon_phase IN ('new','waxing','full','waning','any')) DEFAULT 'any',
    temp_water_min_c REAL,
    temp_water_max_c REAL,
    time_of_day TEXT CHECK(time_of_day IN ('dawn','morning','midday','afternoon','dusk','night','any')) DEFAULT 'any',
    tip_text_fr TEXT NOT NULL,
    tip_text_en TEXT NOT NULL,
    source_url TEXT,
    confidence INTEGER CHECK(confidence BETWEEN 1 AND 5),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tips_species ON tips(species_id);
CREATE INDEX IF NOT EXISTS idx_tips_lookup ON tips(species_id, region_id, water_type_id, season);

CREATE TABLE IF NOT EXISTS solunar_rules (
    id INTEGER PRIMARY KEY,
    period_type TEXT NOT NULL CHECK(period_type IN ('major','minor')),
    duration_minutes INTEGER NOT NULL,
    weight REAL NOT NULL CHECK(weight BETWEEN 0.0 AND 1.0)
);

CREATE TABLE IF NOT EXISTS baro_rules (
    id INTEGER PRIMARY KEY,
    species_id INTEGER NOT NULL REFERENCES species(id),
    baro_trend TEXT NOT NULL CHECK(baro_trend IN ('rising','falling','steady')),
    activity_score INTEGER NOT NULL CHECK(activity_score BETWEEN 1 AND 10),
    notes_fr TEXT,
    notes_en TEXT
);

-- Runtime tables (créées dans le seed mais non bundled)
CREATE TABLE IF NOT EXISTS weather_cache (
    cache_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_sync_meta (
    table_name TEXT PRIMARY KEY,
    last_synced_at TEXT,
    last_etag TEXT,
    row_count INTEGER
);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_schema.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```powershell
git add app\db\__init__.py app\db\schema.sql tests\test_schema.py
git commit -m "feat(phase-0): add SQLite schema with 11 tables and 4 indexes"
```

---

### Task 0.3 : Configure ruff + pre-commit

**Files:**
- Create: `D:\pechepro\.pre-commit-config.yaml`
- Create: `D:\pechepro\.editorconfig`

- [ ] **Step 1: Create .pre-commit-config.yaml**

```yaml
default_install_hook_types: [pre-commit]
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: ['--maxkb=500']
      - id: mixed-line-ending
        args: ['--fix=lf']

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: ['types-requests']
        exclude: ^(tests/|deploy/|data/)
```

- [ ] **Step 2: Create .editorconfig**

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
indent_style = space
indent_size = 4
insert_final_newline = true
trim_trailing_whitespace = true

[*.{md,yml,yaml,json}]
indent_size = 2

[*.{ps1,bat}]
end_of_line = crlf
```

- [ ] **Step 3: Install hooks**

Run: `pre-commit install`
Expected: `pre-commit installed at .git\hooks\pre-commit`

- [ ] **Step 4: Run hooks on all files**

Run: `pre-commit run --all-files`
Expected: all hooks pass (might fix trailing whitespace on existing files — that's OK).

- [ ] **Step 5: Commit**

```powershell
git add .pre-commit-config.yaml .editorconfig
git commit -m "chore(phase-0): configure ruff + mypy + pre-commit hooks"
```

---

### Task 0.4 : Set up GitHub Actions CI workflow

**Files:**
- Create: `D:\pechepro\.github\workflows\test.yml`

- [ ] **Step 1: Write CI workflow**

```yaml
name: Tests

on:
  push:
    branches: [main, "plan/*"]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
          cache: 'pip'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .[dev]
      - name: Run pre-commit
        run: pre-commit run --all-files
      - name: Run tests with coverage
        run: pytest --cov=app --cov-report=term-missing --cov-report=xml -m "not smoke"
      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage-${{ github.sha }}
          path: coverage.xml
          retention-days: 7
```

- [ ] **Step 2: Commit**

```powershell
git add .github\workflows\test.yml
git commit -m "ci(phase-0): add GitHub Actions test workflow on windows-latest"
```

---

### Task 0.5 : Create app/db migrations skeleton + smoke runtime check

**Files:**
- Create: `D:\pechepro\app\db\migrations\__init__.py`
- Create: `D:\pechepro\app\db\migrations\V001_initial.sql`
- Create: `D:\pechepro\tests\test_db_smoke.py`

- [ ] **Step 1: Create migrations/__init__.py**

```python
"""DB migrations runner placeholder. V001_initial.sql is applied via schema.sql for V0.1."""
```

- [ ] **Step 2: Create V001_initial.sql (mirror of schema.sql for migration tracking)**

```sql
-- V001 — initial schema. Identical to schema.sql for V0.1.
-- Future migrations will be V002_*, V003_*, etc.
-- For V0.1, schema.sql is the source of truth; this file exists for future Alembic-style runner.
```

- [ ] **Step 3: Write the smoke test**

Create `D:\pechepro\tests\test_db_smoke.py`:

```python
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_db_smoke.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\db\migrations\__init__.py app\db\migrations\V001_initial.sql tests\test_db_smoke.py
git commit -m "feat(phase-0): add migrations skeleton and disk-DB smoke test"
```

---

### Task 0.6 : Tag phase-0 complete

- [ ] **Step 1: Verify all Phase 0 tests pass**

Run: `pytest -v`
Expected: 4 PASS (3 from test_schema.py + 1 from test_db_smoke.py), 0 fail.

- [ ] **Step 2: Verify coverage targets**

Run: `pytest --cov=app.db --cov-report=term`
Expected: app/db coverage shows reasonable lines covered (schema.sql isn't Python so won't show, but `app/db/__init__.py` should be 100%).

- [ ] **Step 3: Tag and verify**

```powershell
git tag -a phase-0-foundation -m "Phase 0 complete: project structure, schema, CI, pre-commit"
git tag --list
git log --oneline -8
```

Expected: tag `phase-0-foundation` listed; recent commits show Phase 0 work.

---

## Phase 1 — Parallel implementation (3 sub-plans)

Une fois `phase-0-foundation` taggé, démarrer 3 worktrees en parallèle :

```powershell
cd D:\pechepro
git worktree add .claude\worktrees\plan-1-app-core      -b plan/app-core
git worktree add .claude\worktrees\plan-2-services      -b plan/services
git worktree add .claude\worktrees\plan-3-data-curation -b plan/data-curation
```

Suivre :
- [plan-1-app-core.md](2026-05-09-pechepro-plan-1-app-core.md)
- [plan-2-services.md](2026-05-09-pechepro-plan-2-services.md)
- [plan-3-data-curation.md](2026-05-09-pechepro-plan-3-data-curation.md)

**Coordination inter-plans :**
- plan-1 et plan-2 partagent l'API du module `app.db` — celui-ci est livré par Phase 0, donc pas de conflit.
- plan-3 produit des CSVs ; plan-1 lit ces CSVs au seed initial. Si plan-3 finit avant plan-1, parfait. Sinon plan-1 utilise des fixtures de test (5 lignes par table) puis remplace par les CSVs réels lors du merge.
- plan-2 mocke les APIs externes en tests (pas de dépendance plan-3).

**Merge strategy :** chaque worktree merge sur `main` via `git merge --no-ff plan/<name>` après code-review. Tests doivent être verts. Si conflit (peu probable vu la séparation), résoudre dans le worktree.

Une fois les 3 mergés : `git tag -a phase-1-implementation`.

## Phase 2 — Build & deploy

Une fois Phase 1 mergée, suivre [plan-4-build-deploy.md](2026-05-09-pechepro-plan-4-build-deploy.md).

Tag final : `v0.1.0`. Création GitHub release avec asset `pechepro-setup.exe`.
