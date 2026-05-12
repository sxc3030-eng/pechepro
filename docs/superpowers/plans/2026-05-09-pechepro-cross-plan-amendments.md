# Pechepro Cross-Plan Amendments

> **Authoritative document** — this overrides any conflicting signature in plan-1 or plan-2. Read this BEFORE executing any task that calls a service.

**Date :** 2026-05-09
**Status :** Active — applies to plan-1 and plan-2 implementations
**Reason :** Plan-1 (app-core) and plan-2 (services) were drafted in parallel by independent agents. Each interpreted some service signatures slightly differently. This file reconciles them by declaring **canonical signatures** that both plans must follow.

## Canonical service signatures (locked)

These signatures are the contract. Plan-2 implements them as-is. Plan-1 calls them as-is. Any discrepancy in plan-1 task code must be adapted during implementation (the test mocks in plan-1 must also be updated to use these signatures).

```python
# app/services/astral_calc.py
def sun_moon(lat: float, lon: float, date: datetime.date) -> dict[str, Any]:
    """Returns: sunrise, sunset, civil/nautical dawn/dusk, moon_phase, moon_illumination,
    moon_transit, moon_underfoot — all ISO timestamps or floats."""

# app/services/solunar.py
def compute_periods(lat: float, lon: float, date: datetime.date) -> dict[str, Any]:
    """Returns: {'major': [{'start': iso, 'end': iso, 'score': float}, ...], 'minor': [...]}"""

# app/services/baro_analyzer.py
def analyze_trend(pressures_hpa: list[float], hours_window: int = 6) -> str:
    """Returns: 'rising' | 'falling' | 'steady'"""

def species_activity_score(db: sqlite3.Connection, species_id: int, baro_trend: str) -> int:
    """Returns: 1-10 from baro_rules table."""

# app/services/openmeteo_client.py
def get_weather(lat: float, lon: float, db: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Sync wrapper. db param is optional cache backend (weather_cache table, TTL 1h).
    Raises ServiceUnavailable on timeout / 5xx after retries.
    Returns: temp_air_c, pressure_hpa, pressure_trend_6h, humidity_pct, wind_kmh,
             cloud_cover_pct, fetched_at, cached, pressures_history_hpa."""

# app/services/usgs_client.py
def get_water_temp(lat: float, lon: float) -> float | None:
    """Returns Celsius or None (no nearby station / out of US / API error)."""

# app/services/eccc_client.py
def get_water_temp(lat: float, lon: float) -> float | None:
    """Returns Celsius or None."""

# app/services/recommender.py
def recommend(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int | None,
    water_type_id: int | None,
    conditions: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Hierarchical match: exact → region=null → species generic.
    Each result dict: {id, tip_text_fr, tip_text_en, source_url, confidence, match_score}."""

# app/services/data_sync.py
def sync_curated_data(db: sqlite3.Connection, force: bool = False) -> dict[str, list[str]]:
    """Sync CSVs from GitHub raw to SQLite. Skip tables synced <24h ago unless force.
    Returns: {'tables_synced': [...], 'tables_skipped': [...], 'errors': [...]}"""

# app/services/geolocation.py
def get_current_location() -> tuple[float, float] | None:
    """Returns (lat, lon) from Windows Location API, or None if refused/unavailable."""

# app/services/errors.py
class ServiceUnavailable(Exception):
    """Raised by openmeteo / usgs / eccc when a backend is unreachable.
    Plan-1 Flask error handler maps this to HTTP 503."""
```

## Deltas from plan-1's draft contract

Plan-1's "Service interface contract (assumed — implemented by plan-2)" section (lines 19-62) used these signatures. Reconciliation :

| Function | Plan-1 draft (BEFORE) | Canonical (NOW) | Reason |
|---|---|---|---|
| `sun_moon` | `(lat, lon, date: str)` | `(lat, lon, date: datetime.date)` | Type safety; plan-2 implements with `dt.date` |
| `compute_periods` | `(lat, lon, date: str)` | `(lat, lon, date: datetime.date)` | Type safety idem |
| `get_weather` | `(lat, lon)` sync, no db | `(lat, lon, db=None)` sync, optional db | Cache TTL 1h needs db (spec §11 mitigation Open-Meteo rate-limit) |
| `recommend` | `(species_id, region_id, water_type_id, conditions)` | `(db, species_id, region_id, water_type_id, conditions, limit=10)` | recommender queries DB, must take connection |
| `sync_curated_data` | `(db_path: str) -> None` | `(db: sqlite3.Connection, force=False) -> dict` | Pass db connection (consistency), return summary dict for logging |

Plan-2's brief from the dispatch declared async for `get_weather` and `sync_curated_data`. **Reverted to sync** in this amendment because:
- Flask 3 routes are sync by default ; mixing async into sync requires `asyncio.run()` wrappers, adds complexity, no perf gain for a single-user desktop app
- Plan-2 implementations may use `httpx.Client()` (sync) or `asyncio.run(httpx.AsyncClient(...).get(...))` internally — either is fine, but the **public API is sync**

If plan-2's task code currently uses `async def`, change it to `def` during implementation and use sync httpx or wrap async with `asyncio.run()` at the public boundary.

## Impact on plan-1 tasks

These plan-1 tasks need adaptation when executed :

| Task | Current call (plan-1) | Adapted call (canonical) |
|---|---|---|
| Task 14 (`/api/sun-moon`) | `astral_calc.sun_moon(lat, lon, date)` where `date` parsed as str | `astral_calc.sun_moon(lat, lon, datetime.date.fromisoformat(date_str))` |
| Task 15 (`/api/weather`) | `openmeteo_client.get_weather(lat, lon)` | `openmeteo_client.get_weather(lat, lon, db=g.db)` (Flask `g`-pattern) |
| Task 16 (`/api/recommend`) | `recommender.recommend(species_id, region_id, water_type_id, conditions)` | `recommender.recommend(g.db, species_id, region_id, water_type_id, conditions)` |
| Task 17 (`/conditions`) | Same as Tasks 14/15/16 | Apply same adaptations |

For the Flask `g.db` pattern, plan-1 Task 9 (Flask app factory) should add a `before_request` hook that opens the SQLite connection and stores it in `flask.g.db`, and a `teardown_request` hook that closes it. This is a small addition during implementation — not a structural change.

## Impact on plan-2 tasks

Plan-2 tasks should drop `async def` from `get_weather` and `sync_curated_data` and convert to sync. Internal use of `httpx.AsyncClient` is fine but wrapped in `asyncio.run()` at the public function boundary.

Tests that use `pytest-asyncio` for these services should be converted to standard sync tests (drop `@pytest.mark.asyncio` and `await`).

## Verification

After plan-1 + plan-2 are merged on main, run :

```powershell
cd D:\pechepro
.\.venv\Scripts\Activate.ps1
python -c "
from inspect import signature
from app.services import recommender, openmeteo_client, sun_moon, sync_curated_data, get_water_temp
import datetime as dt, sqlite3

# Verify canonical signatures
assert 'db' in str(signature(recommender.recommend))
assert 'limit' in str(signature(recommender.recommend))
assert str(signature(openmeteo_client.get_weather)).startswith('(lat:')
print('Signatures OK')
"
```

Expected output : `Signatures OK`.

## Status

- [ ] Amendment acknowledged in master plan (link added)
- [ ] Plan-1 task implementations adapted as listed above
- [ ] Plan-2 task implementations (`get_weather`, `sync_curated_data`) dropped `async def`
- [ ] Verification snippet passes
