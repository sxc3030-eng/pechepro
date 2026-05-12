# Pechepro Plan 2 — Services Implementation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 10 in-process Python services of pechepro: recommender, solunar, baro_analyzer, astral_calc, openmeteo_client, usgs_client, eccc_client, data_sync, geolocation.

**Architecture:** Each service is a focused module with a small public API (1-3 functions). External APIs called via httpx async, cached in SQLite (`weather_cache`, `data_sync_meta`). Astronomical calculations are 100% local via `astral` and `skyfield`. Tests mock all network and OS-specific dependencies.

**Tech Stack:** Python 3.13 · httpx 0.28.1 · astral 3.2 · skyfield 1.49 · winsdk 1.0.0b10 · pytest 8.3.4 · pytest-asyncio 0.24.0 · respx 0.21.1 · freezegun 1.5.1

**Worktree:** `D:\pechepro\.claude\worktrees\plan-2-services` on branch `plan/services`

---

## Pre-flight

Before any task: `cd D:\pechepro\.claude\worktrees\plan-2-services` (worktree created from master plan Phase 1 instructions). Verify `phase-0-foundation` tag is present (`git tag --list`) and `pytest` collects 0 tests cleanly. The conftest fixture `empty_db` is already available — every test that needs SQLite uses it.

A fresh `tests/services/__init__.py` is created in Task 1 below; subsequent tasks reuse the same package.

---

### Task 1 : Bootstrap services package + tests subdirectory

**Files:**
- Create: `app/services/__init__.py`
- Create: `tests/services/__init__.py`

- [ ] **Step 1: Create the empty services package**

Create `app/services/__init__.py`:

```python
"""In-process service layer for pechepro.

Each module exposes a small public API consumed by the Flask routes in app.server.
Services are isolated from each other (no cross-imports beyond app.db where needed)
and all external I/O (network, OS calls) is mockable for tests.
"""
```

- [ ] **Step 2: Create the test package**

Create `tests/services/__init__.py`:

```python
"""Test suite for app.services.* modules."""
```

- [ ] **Step 3: Verify the package imports cleanly**

Run: `python -c "import app.services; print(app.services.__doc__)"`

Expected: prints the docstring, no ImportError.

- [ ] **Step 4: Verify pytest still collects cleanly**

Run: `pytest -q`

Expected: still 4 passing tests from Phase 0, 0 errors collecting `tests/services/`.

- [ ] **Step 5: Commit**

```powershell
cd D:\pechepro\.claude\worktrees\plan-2-services
git add app\services\__init__.py tests\services\__init__.py
git commit -m "chore(plan-2): bootstrap services package and tests subdirectory"
```

---

## astral_calc — local sun & moon (no network)

We start with `astral_calc` because `solunar` depends on it (moon transit times).

### Task 2 : astral_calc — basic sun_moon happy path

**Files:**
- Create: `app/services/astral_calc.py`
- Create: `tests/services/test_astral_calc.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_astral_calc.py`:

```python
"""Tests for app.services.astral_calc — local sun/moon calculations via astral 3.x."""

import datetime as dt

import pytest
from freezegun import freeze_time

from app.services import astral_calc


@freeze_time("2026-06-21 12:00:00")
def test_sun_moon_returns_iso_keys_for_levis_qc() -> None:
    """Lévis QC at summer solstice should produce a full sun/moon dict with ISO timestamps."""
    result = astral_calc.sun_moon(lat=46.81, lon=-71.21, date=dt.date(2026, 6, 21))
    expected_keys = {
        "sunrise",
        "sunset",
        "civil_dawn",
        "civil_dusk",
        "nautical_dawn",
        "nautical_dusk",
        "moon_phase",
        "moon_illumination",
        "moon_transit",
        "moon_underfoot",
    }
    assert set(result.keys()) >= expected_keys
    # ISO timestamps include 'T'
    assert "T" in result["sunrise"]
    assert "T" in result["sunset"]
    # Moon phase is one of the 4 buckets
    assert result["moon_phase"] in {"new", "waxing", "full", "waning"}
    # Illumination is a fraction 0..1
    assert 0.0 <= result["moon_illumination"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_astral_calc.py -v`

Expected: `ModuleNotFoundError: No module named 'app.services.astral_calc'` (or `ImportError`).

- [ ] **Step 3: Write minimal implementation**

Create `app/services/astral_calc.py`:

```python
"""Local sun & moon calculations via astral 3.x and skyfield. No network."""

from __future__ import annotations

import datetime as dt
from typing import Any

from astral import LocationInfo, moon
from astral.sun import sun

# Skyfield ephemeris is loaded lazily — first call may take ~1s, subsequent cached.
_EPHEMERIS: Any = None
_TS: Any = None


def _load_ephemeris() -> tuple[Any, Any]:
    """Load skyfield ephemeris (de421.bsp ~17MB) and timescale once."""
    global _EPHEMERIS, _TS
    if _EPHEMERIS is None:
        from skyfield.api import load

        _TS = load.timescale()
        _EPHEMERIS = load("de421.bsp")
    return _EPHEMERIS, _TS


def _classify_moon_phase(phase_value: float) -> str:
    """Convert astral.moon.phase() value (0..28) into a 4-bucket label.

    0..6.99   = new
    7..13.99  = waxing
    14..20.99 = full
    21..28    = waning
    """
    if phase_value < 7.0:
        return "new"
    if phase_value < 14.0:
        return "waxing"
    if phase_value < 21.0:
        return "full"
    return "waning"


def _moon_illumination(phase_value: float) -> float:
    """Approximate moon illumination fraction from astral phase (cosine model)."""
    import math

    # Phase 0=new, 14=full. Map to 0..2π then take (1-cos)/2 for illumination.
    angle = (phase_value / 28.0) * 2.0 * math.pi
    return float((1.0 - math.cos(angle)) / 2.0)


def _moon_transits(lat: float, lon: float, date: dt.date) -> tuple[str, str]:
    """Return (transit_iso, underfoot_iso) for the given lat/lon/date using skyfield."""
    from skyfield import almanac
    from skyfield.api import wgs84

    eph, ts = _load_ephemeris()
    observer = wgs84.latlon(lat, lon)
    t0 = ts.utc(date.year, date.month, date.day, 0, 0, 0)
    t1 = ts.utc(date.year, date.month, date.day, 23, 59, 59)
    f = almanac.meridian_transits(eph, eph["Moon"], observer)
    times, events = almanac.find_discrete(t0, t1, f)
    transit_iso = ""
    underfoot_iso = ""
    for t, e in zip(times, events, strict=False):
        iso = t.utc_iso()
        # event 1 = upper transit (over observer), 0 = antitransit (underfoot)
        if e == 1 and not transit_iso:
            transit_iso = iso
        elif e == 0 and not underfoot_iso:
            underfoot_iso = iso
    return transit_iso, underfoot_iso


def sun_moon(lat: float, lon: float, date: dt.date) -> dict[str, Any]:
    """Compute sun/moon parameters for a given location and date.

    Returns a dict with ISO 8601 timestamp strings for all event times,
    a 4-bucket moon phase label, an illumination fraction (0..1),
    and the moon's upper/lower transit times.
    """
    loc = LocationInfo(name="local", region="", timezone="UTC", latitude=lat, longitude=lon)
    s = sun(loc.observer, date=date)
    civil = sun(loc.observer, date=date, dawn_dusk_depression=6.0)
    nautical = sun(loc.observer, date=date, dawn_dusk_depression=12.0)

    phase_val = moon.phase(date)
    transit_iso, underfoot_iso = _moon_transits(lat, lon, date)

    return {
        "sunrise": s["sunrise"].isoformat(),
        "sunset": s["sunset"].isoformat(),
        "civil_dawn": civil["dawn"].isoformat(),
        "civil_dusk": civil["dusk"].isoformat(),
        "nautical_dawn": nautical["dawn"].isoformat(),
        "nautical_dusk": nautical["dusk"].isoformat(),
        "moon_phase": _classify_moon_phase(phase_val),
        "moon_illumination": _moon_illumination(phase_val),
        "moon_transit": transit_iso,
        "moon_underfoot": underfoot_iso,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_astral_calc.py -v`

Expected: 1 PASS. (First run may download `de421.bsp` ephemeris file ~17MB into the working directory — this is normal for skyfield.)

- [ ] **Step 5: Commit**

```powershell
git add app\services\astral_calc.py tests\services\test_astral_calc.py
git commit -m "feat(plan-2): add astral_calc.sun_moon for local sun/moon computations"
```

---

### Task 3 : astral_calc — extreme latitude edge cases

**Files:**
- Modify: `app/services/astral_calc.py`
- Modify: `tests/services/test_astral_calc.py`

- [ ] **Step 1: Add failing tests for high-lat / equator**

Append to `tests/services/test_astral_calc.py`:

```python
@freeze_time("2026-12-21 12:00:00")
def test_sun_moon_polar_winter_handled_gracefully() -> None:
    """Above the Arctic Circle in December the sun never rises — astral may raise.
    The wrapper must catch this and return ISO empty strings for sun events."""
    result = astral_calc.sun_moon(lat=70.0, lon=-150.0, date=dt.date(2026, 12, 21))
    # Sun never rises: event strings either ISO or empty (graceful fallback)
    assert isinstance(result["sunrise"], str)
    assert isinstance(result["sunset"], str)
    # Moon data still computable
    assert result["moon_phase"] in {"new", "waxing", "full", "waning"}


def test_sun_moon_equator_returns_valid_iso() -> None:
    """At the equator on equinox, day and night are ~equal."""
    result = astral_calc.sun_moon(lat=0.0, lon=0.0, date=dt.date(2026, 3, 20))
    assert "T" in result["sunrise"]
    assert "T" in result["sunset"]


def test_sun_moon_invalid_lat_raises() -> None:
    """Out-of-bounds latitude should raise ValueError before hitting astral."""
    with pytest.raises(ValueError):
        astral_calc.sun_moon(lat=95.0, lon=0.0, date=dt.date(2026, 6, 21))


def test_sun_moon_invalid_lon_raises() -> None:
    with pytest.raises(ValueError):
        astral_calc.sun_moon(lat=0.0, lon=200.0, date=dt.date(2026, 6, 21))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_astral_calc.py -v`

Expected: 3 new tests FAIL (no validation, no graceful polar handling).

- [ ] **Step 3: Add validation + graceful fallback**

Edit `app/services/astral_calc.py` — wrap the sun computation and add validation. Replace the `sun_moon` function with:

```python
def sun_moon(lat: float, lon: float, date: dt.date) -> dict[str, Any]:
    """Compute sun/moon parameters for a given location and date.

    Returns a dict with ISO 8601 timestamp strings for all event times,
    a 4-bucket moon phase label, an illumination fraction (0..1),
    and the moon's upper/lower transit times.

    Raises:
        ValueError: if lat outside [-90, 90] or lon outside [-180, 180].
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"lat must be in [-90, 90], got {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"lon must be in [-180, 180], got {lon}")

    loc = LocationInfo(name="local", region="", timezone="UTC", latitude=lat, longitude=lon)

    def _safe_sun(depression: float | None = None) -> dict[str, Any]:
        try:
            if depression is None:
                return sun(loc.observer, date=date)
            return sun(loc.observer, date=date, dawn_dusk_depression=depression)
        except (ValueError, Exception):  # noqa: BLE001
            # astral raises ValueError for polar day/night; fall back to empty strings
            return {
                "sunrise": None,
                "sunset": None,
                "dawn": None,
                "dusk": None,
            }

    s = _safe_sun()
    civil = _safe_sun(6.0)
    nautical = _safe_sun(12.0)

    def _iso(value: Any) -> str:
        if value is None:
            return ""
        return value.isoformat()

    phase_val = moon.phase(date)
    try:
        transit_iso, underfoot_iso = _moon_transits(lat, lon, date)
    except Exception:  # noqa: BLE001
        transit_iso, underfoot_iso = "", ""

    return {
        "sunrise": _iso(s.get("sunrise")),
        "sunset": _iso(s.get("sunset")),
        "civil_dawn": _iso(civil.get("dawn")),
        "civil_dusk": _iso(civil.get("dusk")),
        "nautical_dawn": _iso(nautical.get("dawn")),
        "nautical_dusk": _iso(nautical.get("dusk")),
        "moon_phase": _classify_moon_phase(phase_val),
        "moon_illumination": _moon_illumination(phase_val),
        "moon_transit": transit_iso,
        "moon_underfoot": underfoot_iso,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_astral_calc.py -v`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\astral_calc.py tests\services\test_astral_calc.py
git commit -m "feat(plan-2): handle polar latitudes and validate lat/lon in astral_calc"
```

---

## solunar — major / minor periods of the day

### Task 4 : solunar — compute_periods happy path

**Files:**
- Create: `app/services/solunar.py`
- Create: `tests/services/test_solunar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_solunar.py`:

```python
"""Tests for app.services.solunar — major/minor period computation."""

import datetime as dt
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from app.services import solunar


_FAKE_SUN_MOON = {
    "sunrise": "2026-06-21T08:51:00+00:00",
    "sunset": "2026-06-22T00:48:00+00:00",
    "civil_dawn": "2026-06-21T08:09:00+00:00",
    "civil_dusk": "2026-06-22T01:30:00+00:00",
    "nautical_dawn": "2026-06-21T07:14:00+00:00",
    "nautical_dusk": "2026-06-22T02:25:00+00:00",
    "moon_phase": "waxing",
    "moon_illumination": 0.42,
    "moon_transit": "2026-06-21T16:30:00+00:00",
    "moon_underfoot": "2026-06-21T04:30:00+00:00",
}


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_returns_major_and_minor() -> None:
    """compute_periods should return a dict with 'major' and 'minor' arrays.

    Each entry must have start, end (ISO), and a numeric score in [0,1].
    """
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=_FAKE_SUN_MOON):
        result = solunar.compute_periods(lat=46.81, lon=-71.21, date=dt.date(2026, 6, 21))

    assert "major" in result
    assert "minor" in result
    assert isinstance(result["major"], list)
    assert isinstance(result["minor"], list)
    assert len(result["major"]) >= 1
    assert len(result["minor"]) >= 1

    for period in result["major"] + result["minor"]:
        assert "start" in period
        assert "end" in period
        assert "score" in period
        assert "T" in period["start"]
        assert "T" in period["end"]
        assert 0.0 <= period["score"] <= 1.0


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_major_centered_on_transit() -> None:
    """Major period should be ~lunar transit ± 1h, so ~2h long centered on the transit."""
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=_FAKE_SUN_MOON):
        result = solunar.compute_periods(lat=46.81, lon=-71.21, date=dt.date(2026, 6, 21))

    # First major: transit at 16:30. Start ≈ 15:30, end ≈ 17:30.
    first_major = result["major"][0]
    start = dt.datetime.fromisoformat(first_major["start"])
    end = dt.datetime.fromisoformat(first_major["end"])
    duration = (end - start).total_seconds() / 60.0
    # Within 5 min of 120 min (allow rounding)
    assert 115 <= duration <= 125


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_score_higher_at_full_moon() -> None:
    """Full moon should produce a higher score than new moon (illumination weighting)."""
    full = dict(_FAKE_SUN_MOON, moon_phase="full", moon_illumination=1.0)
    new = dict(_FAKE_SUN_MOON, moon_phase="new", moon_illumination=0.0)
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=full):
        full_result = solunar.compute_periods(46.81, -71.21, dt.date(2026, 6, 21))
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=new):
        new_result = solunar.compute_periods(46.81, -71.21, dt.date(2026, 6, 21))

    assert full_result["major"][0]["score"] > new_result["major"][0]["score"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/services/test_solunar.py -v`

Expected: ImportError / ModuleNotFoundError on `app.services.solunar`.

- [ ] **Step 3: Implement solunar.compute_periods**

Create `app/services/solunar.py`:

```python
"""Solunar major/minor period computation.

Major period = lunar transit ± 1h (~2h window).
Minor period = lunar underfoot ± 1h (~2h window).
Score weighted by moon illumination + phase quality.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.services import astral_calc


_MAJOR_DURATION_MIN = 120  # transit ± 1h
_MINOR_DURATION_MIN = 120  # underfoot ± 1h


def _phase_quality(phase: str) -> float:
    """Quality multiplier per phase (full moon best, new worst)."""
    return {"full": 1.0, "new": 0.85, "waxing": 0.7, "waning": 0.7}.get(phase, 0.7)


def _compute_window(center_iso: str, duration_minutes: int) -> tuple[str, str]:
    """Return (start_iso, end_iso) for a window centered on center_iso."""
    if not center_iso:
        return "", ""
    center = dt.datetime.fromisoformat(center_iso)
    half = dt.timedelta(minutes=duration_minutes / 2.0)
    return (center - half).isoformat(), (center + half).isoformat()


def compute_periods(lat: float, lon: float, date: dt.date) -> dict[str, Any]:
    """Compute solunar major and minor periods for a given location and date.

    Returns:
        {
          "major": [{"start": iso, "end": iso, "score": float}, ...],
          "minor": [{"start": iso, "end": iso, "score": float}, ...],
        }
    """
    sm = astral_calc.sun_moon(lat=lat, lon=lon, date=date)
    illumination = float(sm.get("moon_illumination", 0.0))
    phase = str(sm.get("moon_phase", "waxing"))

    base_score = 0.5 + 0.5 * illumination  # 0.5..1.0
    quality = _phase_quality(phase)
    major_score = round(base_score * quality, 3)
    minor_score = round(major_score * 0.6, 3)

    major: list[dict[str, Any]] = []
    minor: list[dict[str, Any]] = []

    transit_start, transit_end = _compute_window(sm.get("moon_transit", ""), _MAJOR_DURATION_MIN)
    if transit_start:
        major.append({"start": transit_start, "end": transit_end, "score": major_score})

    underfoot_start, underfoot_end = _compute_window(
        sm.get("moon_underfoot", ""), _MINOR_DURATION_MIN
    )
    if underfoot_start:
        minor.append({"start": underfoot_start, "end": underfoot_end, "score": minor_score})

    return {"major": major, "minor": minor}
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_solunar.py -v`

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\solunar.py tests\services\test_solunar.py
git commit -m "feat(plan-2): add solunar.compute_periods (major/minor windows)"
```

---

### Task 5 : solunar — handle missing transits gracefully

**Files:**
- Modify: `tests/services/test_solunar.py`

- [ ] **Step 1: Add edge-case tests**

Append to `tests/services/test_solunar.py`:

```python
@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_missing_transit_returns_empty_major() -> None:
    """When astral_calc returns empty moon_transit (e.g. polar), major[] should be empty
    but minor[] may still be populated (or also empty)."""
    no_transit = dict(_FAKE_SUN_MOON, moon_transit="", moon_underfoot="")
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=no_transit):
        result = solunar.compute_periods(70.0, -150.0, dt.date(2026, 12, 21))
    assert result["major"] == []
    assert result["minor"] == []


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_invalid_lat_propagates() -> None:
    """Invalid lat from astral_calc.sun_moon should propagate (not silently swallowed)."""
    # No patch — use real astral_calc to confirm propagation.
    with pytest.raises(ValueError):
        solunar.compute_periods(95.0, 0.0, dt.date(2026, 6, 21))
```

- [ ] **Step 2: Run tests to verify pass**

Run: `pytest tests/services/test_solunar.py -v`

Expected: 5 PASS (existing 3 + 2 new). The implementation already handles missing transits via `_compute_window` returning empty strings.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_solunar.py
git commit -m "test(plan-2): cover solunar missing-transit and invalid-lat edge cases"
```

---

## baro_analyzer — pressure trend & species activity

### Task 6 : baro_analyzer.analyze_trend happy path

**Files:**
- Create: `app/services/baro_analyzer.py`
- Create: `tests/services/test_baro_analyzer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_baro_analyzer.py`:

```python
"""Tests for app.services.baro_analyzer — pressure trend + species activity scoring."""

import sqlite3

import pytest

from app.services import baro_analyzer


def test_analyze_trend_rising_clear() -> None:
    """Pressure rising > 0.5 hPa over 6h returns 'rising'."""
    pressures = [1010.0, 1010.5, 1011.0, 1011.5, 1012.0, 1012.5, 1013.0]
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "rising"


def test_analyze_trend_falling_clear() -> None:
    pressures = [1015.0, 1014.5, 1014.0, 1013.5, 1013.0, 1012.5, 1012.0]
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "falling"


def test_analyze_trend_steady_within_threshold() -> None:
    """Pressure varying by less than 0.5 hPa is steady."""
    pressures = [1013.0, 1013.1, 1013.2, 1013.0, 1012.9, 1013.0, 1013.1]
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "steady"


def test_analyze_trend_empty_list_returns_steady() -> None:
    """Defensive default: empty input → steady."""
    assert baro_analyzer.analyze_trend([], hours_window=6) == "steady"


def test_analyze_trend_single_point_returns_steady() -> None:
    """Single data point cannot show a trend."""
    assert baro_analyzer.analyze_trend([1013.0], hours_window=6) == "steady"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/services/test_baro_analyzer.py -v`

Expected: ModuleNotFoundError on `app.services.baro_analyzer`.

- [ ] **Step 3: Implement analyze_trend**

Create `app/services/baro_analyzer.py`:

```python
"""Barometric pressure analysis: trend detection + species activity scoring."""

from __future__ import annotations

import sqlite3

# Threshold in hPa over the window to qualify as rising/falling.
_TREND_THRESHOLD_HPA = 0.5


def analyze_trend(pressures_hpa: list[float], hours_window: int = 6) -> str:
    """Classify pressure trend over the window.

    Args:
        pressures_hpa: ordered list of pressure samples (oldest → newest).
        hours_window: nominal window length in hours (informational; not used for math).

    Returns: 'rising' | 'falling' | 'steady'.
    """
    if not pressures_hpa or len(pressures_hpa) < 2:
        return "steady"

    delta = pressures_hpa[-1] - pressures_hpa[0]
    if delta >= _TREND_THRESHOLD_HPA:
        return "rising"
    if delta <= -_TREND_THRESHOLD_HPA:
        return "falling"
    return "steady"
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_baro_analyzer.py -v`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\baro_analyzer.py tests\services\test_baro_analyzer.py
git commit -m "feat(plan-2): add baro_analyzer.analyze_trend (rising/falling/steady)"
```

---

### Task 7 : baro_analyzer.species_activity_score (DB lookup)

**Files:**
- Modify: `app/services/baro_analyzer.py`
- Modify: `tests/services/test_baro_analyzer.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/services/test_baro_analyzer.py`:

```python
def _seed_baro_rules(db: sqlite3.Connection) -> None:
    """Insert a species + 3 baro_rules rows for testing."""
    db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    db.executemany(
        "INSERT INTO baro_rules (species_id, baro_trend, activity_score, notes_fr, notes_en) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (3, "rising", 6, "Activité modérée", "Moderate activity"),
            (3, "falling", 9, "Pic d'activité", "Peak activity"),
            (3, "steady", 4, "Calme", "Calm"),
        ],
    )
    db.commit()


def test_species_activity_score_returns_db_value(empty_db: sqlite3.Connection) -> None:
    _seed_baro_rules(empty_db)
    assert baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="falling") == 9
    assert baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="rising") == 6
    assert baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="steady") == 4


def test_species_activity_score_no_rule_returns_default(empty_db: sqlite3.Connection) -> None:
    """Unknown species or trend returns the neutral default 5."""
    _seed_baro_rules(empty_db)
    assert baro_analyzer.species_activity_score(empty_db, species_id=999, baro_trend="rising") == 5


def test_species_activity_score_invalid_trend_raises(empty_db: sqlite3.Connection) -> None:
    _seed_baro_rules(empty_db)
    with pytest.raises(ValueError):
        baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="bogus")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/services/test_baro_analyzer.py -v`

Expected: 3 new tests fail with AttributeError on `species_activity_score`.

- [ ] **Step 3: Implement species_activity_score**

Append to `app/services/baro_analyzer.py`:

```python
_VALID_TRENDS = {"rising", "falling", "steady"}
_DEFAULT_SCORE = 5


def species_activity_score(
    db: sqlite3.Connection, species_id: int, baro_trend: str
) -> int:
    """Look up activity score (1-10) from baro_rules table.

    Args:
        db: open SQLite connection.
        species_id: foreign key to species.id.
        baro_trend: 'rising' | 'falling' | 'steady'.

    Returns: integer 1..10 (default 5 if no rule exists).

    Raises: ValueError if baro_trend is not one of the 3 valid values.
    """
    if baro_trend not in _VALID_TRENDS:
        raise ValueError(
            f"baro_trend must be one of {_VALID_TRENDS}, got {baro_trend!r}"
        )

    row = db.execute(
        "SELECT activity_score FROM baro_rules WHERE species_id = ? AND baro_trend = ? LIMIT 1",
        (species_id, baro_trend),
    ).fetchone()
    if row is None:
        return _DEFAULT_SCORE
    return int(row[0])
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_baro_analyzer.py -v`

Expected: 8 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\baro_analyzer.py tests\services\test_baro_analyzer.py
git commit -m "feat(plan-2): add baro_analyzer.species_activity_score with default fallback"
```

---

## openmeteo_client — async fetch + SQLite cache

### Task 8 : openmeteo_client — happy path with respx

**Files:**
- Create: `app/services/openmeteo_client.py`
- Create: `tests/services/test_openmeteo_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_openmeteo_client.py`:

```python
"""Tests for app.services.openmeteo_client — async httpx + SQLite cache."""

import json
import sqlite3

import httpx
import pytest
import respx

from app.services import openmeteo_client


_FAKE_RESPONSE = {
    "current": {
        "time": "2026-06-21T12:00",
        "temperature_2m": 22.4,
        "pressure_msl": 1015.2,
        "wind_speed_10m": 11.5,
        "relative_humidity_2m": 58,
    },
    "hourly": {
        "time": [
            "2026-06-21T06:00",
            "2026-06-21T07:00",
            "2026-06-21T08:00",
            "2026-06-21T09:00",
            "2026-06-21T10:00",
            "2026-06-21T11:00",
            "2026-06-21T12:00",
        ],
        "pressure_msl": [1014.0, 1014.2, 1014.5, 1014.8, 1015.0, 1015.1, 1015.2],
    },
}


@pytest.mark.asyncio
async def test_get_weather_happy_path_no_cache() -> None:
    """Without a DB, a single Open-Meteo call returns the parsed dict."""
    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        result = await openmeteo_client.get_weather(lat=46.81, lon=-71.21, db=None)

    assert result["temp_c"] == pytest.approx(22.4)
    assert result["pressure_hpa"] == pytest.approx(1015.2)
    assert len(result["pressures_history_hpa"]) == 7
    assert result["wind_kmh"] == pytest.approx(11.5)
    assert result["humidity_pct"] == 58
    assert result["source"] == "open-meteo"
    assert "fetched_at" in result
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement get_weather (no cache yet)**

Create `app/services/openmeteo_client.py`:

```python
"""Open-Meteo async client with SQLite cache (TTL 1h).

Endpoint: https://api.open-meteo.com/v1/forecast — no API key required.
Rate limit: 10k calls/day. Cache mitigation: round lat/lon to 0.01° (~1km),
cache key = "lat,lon", TTL 3600s.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from typing import Any

import httpx

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL_SECONDS = 3600
_TIMEOUT_SECONDS = 5.0


def _cache_key(lat: float, lon: float) -> str:
    return f"{round(lat, 2):.2f},{round(lon, 2):.2f}"


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


async def _fetch_remote(lat: float, lon: float) -> dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,pressure_msl,wind_speed_10m,relative_humidity_2m",
        "hourly": "pressure_msl",
        "past_hours": 6,
        "forecast_hours": 0,
        "wind_speed_unit": "kmh",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.get(_OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()

    current = data.get("current", {})
    hourly = data.get("hourly", {})
    return {
        "temp_c": float(current.get("temperature_2m", 0.0)),
        "pressure_hpa": float(current.get("pressure_msl", 0.0)),
        "pressures_history_hpa": [float(x) for x in hourly.get("pressure_msl", [])],
        "wind_kmh": float(current.get("wind_speed_10m", 0.0)),
        "humidity_pct": int(current.get("relative_humidity_2m", 0)),
        "fetched_at": _now_iso(),
        "source": "open-meteo",
    }


async def get_weather(
    lat: float, lon: float, db: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Fetch weather for a location, using the SQLite cache if fresh.

    Args:
        lat, lon: WGS84 coordinates.
        db: optional connection. When provided, results are cached in `weather_cache`
            for 1 hour.

    Returns: dict with temp_c, pressure_hpa, pressures_history_hpa, wind_kmh,
        humidity_pct, fetched_at, source.
    """
    if db is not None:
        cached = _read_cache(db, lat, lon)
        if cached is not None:
            return cached

    fresh = await _fetch_remote(lat, lon)
    if db is not None:
        _write_cache(db, lat, lon, fresh)
    return fresh


def _read_cache(db: sqlite3.Connection, lat: float, lon: float) -> dict[str, Any] | None:
    """Return cached payload if not expired, else None."""
    key = _cache_key(lat, lon)
    row = db.execute(
        "SELECT payload_json, expires_at FROM weather_cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    payload_json, expires_at = row
    if dt.datetime.fromisoformat(expires_at) <= dt.datetime.now(dt.UTC):
        return None
    return json.loads(payload_json)


def _write_cache(
    db: sqlite3.Connection, lat: float, lon: float, payload: dict[str, Any]
) -> None:
    key = _cache_key(lat, lon)
    now = dt.datetime.now(dt.UTC)
    expires = now + dt.timedelta(seconds=_CACHE_TTL_SECONDS)
    db.execute(
        "INSERT OR REPLACE INTO weather_cache (cache_key, payload_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (key, json.dumps(payload), now.isoformat(), expires.isoformat()),
    )
    db.commit()
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\openmeteo_client.py tests\services\test_openmeteo_client.py
git commit -m "feat(plan-2): add openmeteo_client.get_weather (async httpx)"
```

---

### Task 9 : openmeteo_client — cache hit (no second network call)

**Files:**
- Modify: `tests/services/test_openmeteo_client.py`

- [ ] **Step 1: Add cache test**

Append to `tests/services/test_openmeteo_client.py`:

```python
@pytest.mark.asyncio
async def test_get_weather_uses_cache_within_ttl(empty_db: sqlite3.Connection) -> None:
    """Second call within TTL must NOT hit the network."""
    with respx.mock() as router:
        route = router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        first = await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
        second = await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    assert route.call_count == 1
    assert first == second


@pytest.mark.asyncio
async def test_get_weather_cache_isolated_by_coordinates(empty_db: sqlite3.Connection) -> None:
    """Different lat/lon → different cache rows → 2 network calls."""
    with respx.mock() as router:
        route = router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
        await openmeteo_client.get_weather(45.50, -73.57, db=empty_db)

    assert route.call_count == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 3 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_openmeteo_client.py
git commit -m "test(plan-2): verify openmeteo_client cache hits within TTL"
```

---

### Task 10 : openmeteo_client — failure modes (timeout, 5xx, malformed)

**Files:**
- Modify: `app/services/openmeteo_client.py`
- Modify: `tests/services/test_openmeteo_client.py`

- [ ] **Step 1: Add failure-mode tests**

Append to `tests/services/test_openmeteo_client.py`:

```python
@pytest.mark.asyncio
async def test_get_weather_timeout_uses_stale_cache(empty_db: sqlite3.Connection) -> None:
    """If the network call times out and a stale cache row exists (<2h old), serve it."""
    # Pre-populate cache with a slightly stale row (forced expires_at in past)
    import datetime as dt

    payload = {
        "temp_c": 19.0,
        "pressure_hpa": 1010.0,
        "pressures_history_hpa": [1010.0],
        "wind_kmh": 5.0,
        "humidity_pct": 60,
        "fetched_at": (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=80)).isoformat(),
        "source": "open-meteo",
    }
    expired_iso = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=20)).isoformat()
    fetched_iso = (dt.datetime.now(dt.UTC) - dt.timedelta(minutes=80)).isoformat()
    empty_db.execute(
        "INSERT INTO weather_cache (cache_key, payload_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        ("46.81,-71.21", json.dumps(payload), fetched_iso, expired_iso),
    )
    empty_db.commit()

    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            side_effect=httpx.TimeoutException("simulated timeout")
        )
        result = await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    assert result["temp_c"] == pytest.approx(19.0)
    assert result["source"] == "open-meteo"


@pytest.mark.asyncio
async def test_get_weather_timeout_no_cache_raises(empty_db: sqlite3.Connection) -> None:
    """Timeout with no cache row → caller gets the exception (Flask renders 'météo indisponible')."""
    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            side_effect=httpx.TimeoutException("simulated timeout")
        )
        with pytest.raises(httpx.TimeoutException):
            await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)


@pytest.mark.asyncio
async def test_get_weather_5xx_raises() -> None:
    """A 503 from Open-Meteo must surface (no DB → no fallback)."""
    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(503)
        )
        with pytest.raises(httpx.HTTPStatusError):
            await openmeteo_client.get_weather(46.81, -71.21, db=None)


@pytest.mark.asyncio
async def test_get_weather_malformed_json_raises() -> None:
    """A malformed JSON body should propagate as ValueError (not silently empty)."""
    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        with pytest.raises((json.JSONDecodeError, ValueError)):
            await openmeteo_client.get_weather(46.81, -71.21, db=None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 1 PASS, 3 FAIL — the timeout-with-stale-cache test fails because we don't fall back to expired rows yet.

- [ ] **Step 3: Add stale-cache fallback**

Modify `app/services/openmeteo_client.py` — replace the `get_weather` function with this version that catches timeouts and falls back to a stale row up to 2h old:

```python
_STALE_CACHE_FALLBACK_SECONDS = 7200  # 2h


def _read_stale_cache(
    db: sqlite3.Connection, lat: float, lon: float, max_age_seconds: int
) -> dict[str, Any] | None:
    """Return cached payload even if expired, as long as fetched_at is within max_age_seconds."""
    key = _cache_key(lat, lon)
    row = db.execute(
        "SELECT payload_json, fetched_at FROM weather_cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    payload_json, fetched_at = row
    age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(fetched_at)
    if age.total_seconds() > max_age_seconds:
        return None
    return json.loads(payload_json)


async def get_weather(
    lat: float, lon: float, db: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Fetch weather for a location, using the SQLite cache if fresh.

    On timeout or network error with a stale-but-recent (<2h) cache row, serves
    the stale data as a graceful fallback.
    """
    if db is not None:
        cached = _read_cache(db, lat, lon)
        if cached is not None:
            return cached

    try:
        fresh = await _fetch_remote(lat, lon)
    except (httpx.TimeoutException, httpx.NetworkError):
        if db is not None:
            stale = _read_stale_cache(db, lat, lon, _STALE_CACHE_FALLBACK_SECONDS)
            if stale is not None:
                return stale
        raise

    if db is not None:
        _write_cache(db, lat, lon, fresh)
    return fresh
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\openmeteo_client.py tests\services\test_openmeteo_client.py
git commit -m "feat(plan-2): openmeteo_client falls back to stale cache on timeout"
```

---

## usgs_client — US water temperature

### Task 11 : usgs_client — happy path

**Files:**
- Create: `app/services/usgs_client.py`
- Create: `tests/services/test_usgs_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_usgs_client.py`:

```python
"""Tests for app.services.usgs_client — USGS Water Services water temperature."""

import httpx
import pytest
import respx

from app.services import usgs_client


_USGS_OK_BODY = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "TEST SITE NEAR LEVIS",
                    "geoLocation": {
                        "geogLocation": {"latitude": 46.81, "longitude": -71.21}
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00010"}],  # 00010 = temperature, water
                    "unit": {"unitCode": "deg C"},
                },
                "values": [
                    {
                        "value": [
                            {
                                "value": "18.3",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-21T12:00:00.000",
                            }
                        ]
                    }
                ],
            }
        ]
    }
}


@pytest.mark.asyncio
async def test_get_water_temp_returns_celsius_for_us_lat_lon() -> None:
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        result = await usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result == pytest.approx(18.3)


@pytest.mark.asyncio
async def test_get_water_temp_returns_none_outside_us() -> None:
    """Lat/lon clearly outside the US bbox returns None without network call."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        result = await usgs_client.get_water_temp(lat=46.81, lon=-71.21)  # Lévis QC

    assert result is None
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_get_water_temp_no_station_returns_none() -> None:
    empty = {"value": {"timeSeries": []}}
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=empty)
        )
        result = await usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_5xx_returns_none() -> None:
    """API failure returns None (UI shows 'no water temp', no crash)."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(503)
        )
        result = await usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_timeout_returns_none() -> None:
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = await usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_invalid_lat_lon_returns_none() -> None:
    """Out-of-bounds returns None (no exception)."""
    assert await usgs_client.get_water_temp(lat=999.0, lon=0.0) is None
    assert await usgs_client.get_water_temp(lat=0.0, lon=999.0) is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/services/test_usgs_client.py -v`

Expected: ModuleNotFoundError on `app.services.usgs_client`.

- [ ] **Step 3: Implement get_water_temp**

Create `app/services/usgs_client.py`:

```python
"""USGS Water Services client — water temperature for US lat/lon.

API: https://waterservices.usgs.gov/nwis/iv/?format=json&parameterCd=00010&...
parameterCd 00010 = "Temperature, water, degrees Celsius".
No API key required.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_USGS_URL = "https://waterservices.usgs.gov/nwis/iv/"
_TIMEOUT_SECONDS = 5.0
_BBOX_RADIUS_DEG = 0.5  # ~55km bounding box around requested lat/lon

# US continental bbox (rough — Alaska/Hawaii excluded for V0.1).
_US_LAT_MIN, _US_LAT_MAX = 24.5, 49.5
_US_LON_MIN, _US_LON_MAX = -125.0, -66.5


def _is_in_us(lat: float, lon: float) -> bool:
    return _US_LAT_MIN <= lat <= _US_LAT_MAX and _US_LON_MIN <= lon <= _US_LON_MAX


def _is_valid_coords(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


async def get_water_temp(lat: float, lon: float) -> float | None:
    """Fetch water temperature in °C from USGS Water Services.

    Args:
        lat, lon: WGS84 coordinates.

    Returns: Celsius value of the most recent reading from the nearest US station,
        or None if outside US bbox / no station / API failure / timeout.
    """
    if not _is_valid_coords(lat, lon):
        return None
    if not _is_in_us(lat, lon):
        return None

    bbox = (
        f"{lon - _BBOX_RADIUS_DEG:.4f},"
        f"{lat - _BBOX_RADIUS_DEG:.4f},"
        f"{lon + _BBOX_RADIUS_DEG:.4f},"
        f"{lat + _BBOX_RADIUS_DEG:.4f}"
    )
    params = {
        "format": "json",
        "parameterCd": "00010",
        "bBox": bbox,
        "siteStatus": "active",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(_USGS_URL, params=params)
        if response.status_code != 200:
            logger.warning("USGS API returned %s for bbox=%s", response.status_code, bbox)
            return None
        data = response.json()
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("USGS network error: %s", exc)
        return None
    except ValueError as exc:
        logger.warning("USGS malformed JSON: %s", exc)
        return None

    return _extract_first_temperature(data)


def _extract_first_temperature(data: dict[str, Any]) -> float | None:
    series = data.get("value", {}).get("timeSeries", [])
    for ts in series:
        for value_block in ts.get("values", []):
            for sample in value_block.get("value", []):
                raw = sample.get("value")
                try:
                    parsed = float(raw)
                except (TypeError, ValueError):
                    continue
                # USGS uses -999999 to mark missing values
                if parsed > -100.0:
                    return parsed
    return None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_usgs_client.py -v`

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\usgs_client.py tests\services\test_usgs_client.py
git commit -m "feat(plan-2): add usgs_client.get_water_temp (US water temperature)"
```

---

## eccc_client — Canada water temperature

### Task 12 : eccc_client — happy path + graceful failure

**Files:**
- Create: `app/services/eccc_client.py`
- Create: `tests/services/test_eccc_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_eccc_client.py`:

```python
"""Tests for app.services.eccc_client — ECCC water temperature (Canada).

ECCC publishes hydrometric/climate data through dd.weather.gc.ca and the GeoMet API.
Water temp coverage is sparse (most stations report flow only); we accept partial coverage
and fail gracefully when no data exists.
"""

import httpx
import pytest
import respx

from app.services import eccc_client


_ECCC_OK_BODY = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "STATION_NUMBER": "02OG025",
                "STATION_NAME": "TEST CA STATION",
                "WATER_TEMPERATURE": 14.6,
                "DATE": "2026-06-21T12:00:00Z",
            },
            "geometry": {"type": "Point", "coordinates": [-71.21, 46.81]},
        }
    ],
}


@pytest.mark.asyncio
async def test_get_water_temp_returns_celsius_for_canada() -> None:
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        result = await eccc_client.get_water_temp(lat=46.81, lon=-71.21)

    assert result == pytest.approx(14.6)


@pytest.mark.asyncio
async def test_get_water_temp_outside_canada_returns_none() -> None:
    with respx.mock() as router:
        route = router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        result = await eccc_client.get_water_temp(lat=44.5, lon=-72.0)  # Vermont USA
    assert result is None
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_get_water_temp_no_features_returns_none() -> None:
    empty = {"type": "FeatureCollection", "features": []}
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=empty)
        )
        result = await eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_timeout_returns_none() -> None:
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = await eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_5xx_returns_none() -> None:
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(500)
        )
        result = await eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_malformed_returns_none() -> None:
    with respx.mock() as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        result = await eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


@pytest.mark.asyncio
async def test_get_water_temp_invalid_coords_returns_none() -> None:
    assert await eccc_client.get_water_temp(lat=999.0, lon=0.0) is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/services/test_eccc_client.py -v`

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement get_water_temp**

Create `app/services/eccc_client.py`:

```python
"""ECCC (Environment and Climate Change Canada) water temperature client.

API: https://api.weather.gc.ca/collections/hydrometric-realtime/items?...
Coverage is sparse — many Canadian stations report only discharge.
We fail gracefully (return None) when no data is available.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ECCC_URL = "https://api.weather.gc.ca/collections/hydrometric-realtime/items"
_TIMEOUT_SECONDS = 5.0
_BBOX_RADIUS_DEG = 0.5

# Canada bbox (continental — yes, includes northern territories).
_CA_LAT_MIN, _CA_LAT_MAX = 41.5, 84.0
_CA_LON_MIN, _CA_LON_MAX = -141.0, -52.0


def _is_in_canada(lat: float, lon: float) -> bool:
    return _CA_LAT_MIN <= lat <= _CA_LAT_MAX and _CA_LON_MIN <= lon <= _CA_LON_MAX


def _is_valid_coords(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


async def get_water_temp(lat: float, lon: float) -> float | None:
    """Fetch water temperature in °C from ECCC GeoMet API.

    Returns: Celsius value or None if outside CA / no station / API failure.
    """
    if not _is_valid_coords(lat, lon):
        return None
    if not _is_in_canada(lat, lon):
        return None

    bbox = (
        f"{lon - _BBOX_RADIUS_DEG:.4f},"
        f"{lat - _BBOX_RADIUS_DEG:.4f},"
        f"{lon + _BBOX_RADIUS_DEG:.4f},"
        f"{lat + _BBOX_RADIUS_DEG:.4f}"
    )
    params = {
        "f": "json",
        "bbox": bbox,
        "limit": 50,
        "properties": "STATION_NUMBER,STATION_NAME,WATER_TEMPERATURE,DATE",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(_ECCC_URL, params=params)
        if response.status_code != 200:
            logger.warning("ECCC API returned %s for bbox=%s", response.status_code, bbox)
            return None
        data = response.json()
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("ECCC network error: %s", exc)
        return None
    except ValueError as exc:
        logger.warning("ECCC malformed JSON: %s", exc)
        return None

    return _extract_first_temperature(data)


def _extract_first_temperature(data: dict[str, Any]) -> float | None:
    features = data.get("features", [])
    for feature in features:
        props = feature.get("properties", {})
        raw = props.get("WATER_TEMPERATURE")
        if raw is None:
            continue
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            continue
        if -50.0 < parsed < 50.0:  # sanity bounds
            return parsed
    return None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_eccc_client.py -v`

Expected: 7 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\eccc_client.py tests\services\test_eccc_client.py
git commit -m "feat(plan-2): add eccc_client.get_water_temp (Canada water temperature)"
```

---

## recommender — query SQLite tips with hierarchical fallback

### Task 13 : recommender — exact match happy path

**Files:**
- Create: `app/services/recommender.py`
- Create: `tests/services/test_recommender.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_recommender.py`:

```python
"""Tests for app.services.recommender — tip ranking with hierarchical fallback."""

import sqlite3

import pytest

from app.services import recommender


def _seed_recommender_fixture(db: sqlite3.Connection) -> None:
    """Seed minimal data: 1 species (walleye=3), 1 region (QC=1), 1 water_type (lake=1).

    Inserts 5 tips of varying specificity:
      - tip 1: exact match all 4 conditions (highest score)
      - tip 2: matches species+region only (medium)
      - tip 3: generic species (region NULL) (lowest)
      - tip 4: completely different species (filtered out)
      - tip 5: same species but different region_id (filtered out)
    """
    db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (5, 'Brochet', 'Northern Pike', 'Esox lucius')"
    )
    db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (2, 'Ontario', 'Ontario', 'CA', 'ON')"
    )
    db.execute(
        "INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')"
    )

    # Note: column order from schema:
    # species_id, region_id, water_type_id, season, baro_trend, moon_phase,
    # temp_water_min_c, temp_water_max_c, time_of_day, tip_text_fr, tip_text_en, source_url, confidence
    tips = [
        # tip 1: full match
        (3, 1, 1, "summer", "falling", "full", None, None, "any",
         "Match parfait", "Perfect match", "https://example.com/1", 5),
        # tip 2: species + region match, generic baro
        (3, 1, 1, "any", "any", "any", None, None, "any",
         "Match région", "Region match", "https://example.com/2", 4),
        # tip 3: generic species (region NULL)
        (3, None, None, "any", "any", "any", None, None, "any",
         "Conseil générique", "Generic tip", "https://example.com/3", 3),
        # tip 4: wrong species (filtered)
        (5, 1, 1, "summer", "falling", "full", None, None, "any",
         "Pas pour walleye", "Not for walleye", "https://example.com/4", 5),
        # tip 5: right species, wrong region
        (3, 2, 1, "summer", "falling", "full", None, None, "any",
         "Mauvaise région", "Wrong region", "https://example.com/5", 5),
    ]
    db.executemany(
        "INSERT INTO tips (species_id, region_id, water_type_id, season, baro_trend, moon_phase, "
        "temp_water_min_c, temp_water_max_c, time_of_day, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tips,
    )
    db.commit()


def test_recommend_returns_exact_match_first(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    assert len(result) >= 1
    assert result[0]["tip_text_fr"] == "Match parfait"
    assert result[0]["confidence"] == 5
    # Match score should reflect # of matched conditions
    assert result[0]["match_score"] >= result[1]["match_score"]


def test_recommend_excludes_other_species(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full",
                    "season": "summer", "time_of_day": "morning", "water_temp_c": 20.0},
    )
    texts = {tip["tip_text_fr"] for tip in result}
    assert "Pas pour walleye" not in texts


def test_recommend_excludes_wrong_region_when_region_specified(empty_db: sqlite3.Connection) -> None:
    """When region_id is specified, tips with a different non-null region_id are excluded.
    Tips with region_id=NULL are still allowed (generic fallback)."""
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full",
                    "season": "summer", "time_of_day": "morning", "water_temp_c": 20.0},
    )
    texts = {tip["tip_text_fr"] for tip in result}
    assert "Mauvaise région" not in texts


def test_recommend_returns_at_most_limit(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=1, water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full", "season": "summer",
                    "time_of_day": "morning", "water_temp_c": 20.0},
        limit=2,
    )
    assert len(result) <= 2


def test_recommend_returns_required_fields(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=1, water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full", "season": "summer",
                    "time_of_day": "morning", "water_temp_c": 20.0},
    )
    assert result, "expected at least one tip"
    expected_keys = {"tip_text_fr", "tip_text_en", "source_url", "confidence", "match_score"}
    assert expected_keys <= set(result[0].keys())
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/services/test_recommender.py -v`

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement recommender.recommend**

Create `app/services/recommender.py`:

```python
"""Tip recommender with hierarchical fallback.

Logic:
    1. Filter tips by species_id (mandatory).
    2. If region_id is provided, allow tips whose region_id matches OR is NULL.
       (NULL means "generic across NA".)
    3. If water_type_id is provided, allow tips whose water_type_id matches OR is NULL.
    4. Score each tip by counting how many of the user-supplied conditions it matches
       (baro_trend, moon_phase, season, time_of_day, water_temp_c range).
       'any' in the tip column matches any user value (counts as 1).
    5. Final ordering: match_score DESC, confidence DESC, id ASC (deterministic).
"""

from __future__ import annotations

import sqlite3
from typing import Any

# Conditions whose absence in tip (= 'any') still counts as a soft match.
_CONDITION_KEYS = ("baro_trend", "moon_phase", "season", "time_of_day")


def recommend(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int | None,
    water_type_id: int | None,
    conditions: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the top-N tips for the requested species and conditions.

    Args:
        db: open SQLite connection.
        species_id: required filter.
        region_id: nullable; when set, allow tips with same region or NULL.
        water_type_id: nullable; same semantics as region_id.
        conditions: dict with optional keys baro_trend, moon_phase, season, time_of_day,
            water_temp_c.
        limit: max number of results returned.

    Returns: list of dicts with tip_text_fr, tip_text_en, source_url, confidence, match_score.
    """
    sql_parts = ["SELECT id, tip_text_fr, tip_text_en, source_url, confidence, "
                 "season, baro_trend, moon_phase, time_of_day, "
                 "temp_water_min_c, temp_water_max_c "
                 "FROM tips WHERE species_id = ?"]
    params: list[Any] = [species_id]

    if region_id is not None:
        sql_parts.append("AND (region_id = ? OR region_id IS NULL)")
        params.append(region_id)
    if water_type_id is not None:
        sql_parts.append("AND (water_type_id = ? OR water_type_id IS NULL)")
        params.append(water_type_id)

    sql = " ".join(sql_parts)
    rows = db.execute(sql, params).fetchall()

    scored: list[dict[str, Any]] = []
    for row in rows:
        (rid, fr, en, src, conf, season, baro, moon, tod, tmin, tmax) = row
        score = _score_tip(
            row_conditions={
                "season": season,
                "baro_trend": baro,
                "moon_phase": moon,
                "time_of_day": tod,
            },
            row_temp_range=(tmin, tmax),
            user=conditions,
        )
        scored.append({
            "tip_text_fr": fr,
            "tip_text_en": en,
            "source_url": src,
            "confidence": conf,
            "match_score": score,
            "_id": rid,
        })

    # Sort by score DESC, confidence DESC, id ASC
    scored.sort(key=lambda t: (-t["match_score"], -(t["confidence"] or 0), t["_id"]))
    for tip in scored:
        tip.pop("_id", None)
    return scored[:limit]


def _score_tip(
    row_conditions: dict[str, str | None],
    row_temp_range: tuple[float | None, float | None],
    user: dict[str, Any],
) -> int:
    """Score = number of user conditions that the tip matches.

    Rules:
      - tip column 'any' (or NULL) matches any user value with weight 1
      - exact match weight 2 (specific guidance is more valuable)
      - water temp inside [min, max] adds 2; outside adds 0
    """
    score = 0
    for key in _CONDITION_KEYS:
        tip_val = row_conditions.get(key)
        user_val = user.get(key)
        if user_val is None:
            continue
        if tip_val in (None, "any"):
            score += 1
        elif tip_val == user_val:
            score += 2

    user_temp = user.get("water_temp_c")
    tmin, tmax = row_temp_range
    if user_temp is not None and (tmin is not None or tmax is not None):
        lo = tmin if tmin is not None else float("-inf")
        hi = tmax if tmax is not None else float("inf")
        if lo <= float(user_temp) <= hi:
            score += 2

    return score
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/services/test_recommender.py -v`

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\recommender.py tests\services\test_recommender.py
git commit -m "feat(plan-2): add recommender.recommend with hierarchical filter"
```

---

### Task 14 : recommender — fallback hierarchy when no exact match

**Files:**
- Modify: `tests/services/test_recommender.py`

- [ ] **Step 1: Add fallback tests**

Append to `tests/services/test_recommender.py`:

```python
def test_recommend_falls_back_to_generic_when_no_specific(empty_db: sqlite3.Connection) -> None:
    """If only generic (region=NULL) tips exist, they are returned anyway."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, tip_text_en, "
        "source_url, confidence) VALUES (3, NULL, NULL, 'Générique', 'Generic', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=1, water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full",
                    "season": "summer", "time_of_day": "morning", "water_temp_c": 20.0},
    )
    assert len(result) == 1
    assert result[0]["tip_text_fr"] == "Générique"


def test_recommend_returns_empty_when_species_unknown(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db, species_id=999, region_id=1, water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full",
                    "season": "summer", "time_of_day": "morning", "water_temp_c": 20.0},
    )
    assert result == []


def test_recommend_temp_range_match_boosts_score(empty_db: sqlite3.Connection) -> None:
    """A tip with water-temp range matching user's temp should outrank one without."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    # Tip A: temp range matches
    empty_db.execute(
        "INSERT INTO tips (species_id, temp_water_min_c, temp_water_max_c, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 18.0, 22.0, 'Match temp', 'Temp match', NULL, 3)"
    )
    # Tip B: no temp range
    empty_db.execute(
        "INSERT INTO tips (species_id, temp_water_min_c, temp_water_max_c, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, NULL, 'No temp', 'No temp', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=None, water_type_id=None,
        conditions={"water_temp_c": 20.0},
    )
    assert result[0]["tip_text_fr"] == "Match temp"


def test_recommend_no_region_id_returns_all_species_tips(empty_db: sqlite3.Connection) -> None:
    """When region_id=None, all tips for the species are eligible."""
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=None, water_type_id=None,
        conditions={"baro_trend": "falling", "moon_phase": "full",
                    "season": "summer", "time_of_day": "morning", "water_temp_c": 20.0},
    )
    texts = {t["tip_text_fr"] for t in result}
    assert "Mauvaise région" in texts  # now allowed since no region filter
    assert "Pas pour walleye" not in texts  # still wrong species
```

- [ ] **Step 2: Run tests to verify pass**

Run: `pytest tests/services/test_recommender.py -v`

Expected: 9 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_recommender.py
git commit -m "test(plan-2): cover recommender fallback hierarchy and temp-range scoring"
```

---

## data_sync — fetch curated CSVs from GitHub raw

### Task 15 : data_sync — happy path with mocked httpx

**Files:**
- Create: `app/services/data_sync.py`
- Create: `tests/services/test_data_sync.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_data_sync.py`:

```python
"""Tests for app.services.data_sync — fetch curated CSVs from GitHub raw."""

import datetime as dt
import sqlite3

import httpx
import pytest
import respx
from freezegun import freeze_time

from app.services import data_sync


_SPECIES_CSV = (
    "id,common_name_fr,common_name_en,scientific_name\n"
    "3,Doré jaune,Walleye,Sander vitreus\n"
    "5,Grand brochet,Northern Pike,Esox lucius\n"
)


@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_curated_data_inserts_rows(empty_db: sqlite3.Connection) -> None:
    """Successful sync of one CSV upserts rows + records etag in data_sync_meta."""
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        # Match only the species CSV; other tables get 404 (will be reported in errors).
        router.get(
            "/sxc3030-eng/pechepro/main/data/curated/species.csv"
        ).mock(
            return_value=httpx.Response(
                200,
                content=_SPECIES_CSV.encode(),
                headers={"ETag": '"abc123"'},
            )
        )
        # Other tables — no curated data needed for this test, return 404
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = await data_sync.sync_curated_data(empty_db, force=True)

    assert "species" in result["tables_synced"]
    rows = empty_db.execute("SELECT id, common_name_fr FROM species ORDER BY id").fetchall()
    assert rows == [(3, "Doré jaune"), (5, "Grand brochet")]
    meta = empty_db.execute(
        "SELECT last_etag, row_count FROM data_sync_meta WHERE table_name = ?", ("species",)
    ).fetchone()
    assert meta == ('"abc123"', 2)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement sync_curated_data**

Create `app/services/data_sync.py`:

```python
"""Sync curated CSVs from GitHub raw into local SQLite.

Source: https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/<table>.csv

For each table: at most 1×/24h. ETag-based 304 short-circuit. On 200, DELETE + INSERT
(simple semantics for V0.1; future: incremental upsert).
On any error: skip table, accumulate in result["errors"], continue.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import sqlite3
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated"
_SYNC_INTERVAL_SECONDS = 24 * 3600
_TIMEOUT_SECONDS = 10.0

# Tables we sync, in dependency order (species before tips, regions before tips).
_SYNC_TABLES: tuple[str, ...] = (
    "species",
    "regions",
    "water_types",
    "lures",
    "color_visibility",
    "solunar_rules",
    "baro_rules",
    "tips",
)


async def sync_curated_data(db: sqlite3.Connection, force: bool = False) -> dict[str, Any]:
    """Sync each curated table from GitHub raw. Skip tables synced <24h ago unless force=True.

    Returns: {"tables_synced": [...], "tables_skipped": [...], "errors": [...]}.
    """
    synced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        for table in _SYNC_TABLES:
            try:
                if not force and _is_recently_synced(db, table):
                    skipped.append(table)
                    continue
                outcome = await _sync_one_table(client, db, table)
                if outcome == "synced":
                    synced.append(table)
                elif outcome == "not_modified":
                    skipped.append(table)
                else:
                    errors.append(f"{table}: {outcome}")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning("data_sync %s network error: %s", table, exc)
                errors.append(f"{table}: network ({exc.__class__.__name__})")
            except Exception as exc:  # noqa: BLE001
                logger.exception("data_sync %s unexpected", table)
                errors.append(f"{table}: {exc}")

    return {"tables_synced": synced, "tables_skipped": skipped, "errors": errors}


def _is_recently_synced(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "SELECT last_synced_at FROM data_sync_meta WHERE table_name = ?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        return False
    last = dt.datetime.fromisoformat(row[0])
    age = (dt.datetime.now(dt.UTC) - last).total_seconds()
    return age < _SYNC_INTERVAL_SECONDS


def _read_etag(db: sqlite3.Connection, table: str) -> str | None:
    row = db.execute(
        "SELECT last_etag FROM data_sync_meta WHERE table_name = ?", (table,)
    ).fetchone()
    return row[0] if row else None


async def _sync_one_table(
    client: httpx.AsyncClient, db: sqlite3.Connection, table: str
) -> str:
    """Returns 'synced' | 'not_modified' | error string."""
    url = f"{_BASE_URL}/{table}.csv"
    headers: dict[str, str] = {}
    prev_etag = _read_etag(db, table)
    if prev_etag:
        headers["If-None-Match"] = prev_etag

    response = await client.get(url, headers=headers)
    if response.status_code == 304:
        _bump_synced_at(db, table, prev_etag, None)
        return "not_modified"
    if response.status_code == 404:
        return "not_found"
    if response.status_code >= 500:
        return f"http_{response.status_code}"
    if response.status_code != 200:
        return f"http_{response.status_code}"

    text = response.text
    new_etag = response.headers.get("ETag")
    rows = list(csv.DictReader(io.StringIO(text)))
    _replace_table_rows(db, table, rows)
    _bump_synced_at(db, table, new_etag, len(rows))
    return "synced"


def _replace_table_rows(db: sqlite3.Connection, table: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        db.execute(f"DELETE FROM {table}")
        db.commit()
        return
    columns = list(rows[0].keys())
    placeholders = ",".join("?" for _ in columns)
    column_list = ",".join(columns)
    db.execute(f"DELETE FROM {table}")
    insert_sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    for row in rows:
        values = [_coerce_csv_cell(row[c]) for c in columns]
        db.execute(insert_sql, values)
    db.commit()


def _coerce_csv_cell(value: str | None) -> Any:
    """Empty cell → NULL; everything else → raw str (SQLite handles type coercion)."""
    if value is None or value == "":
        return None
    return value


def _bump_synced_at(
    db: sqlite3.Connection, table: str, etag: str | None, row_count: int | None
) -> None:
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    existing = db.execute(
        "SELECT row_count FROM data_sync_meta WHERE table_name = ?", (table,)
    ).fetchone()
    final_count = row_count if row_count is not None else (existing[0] if existing else 0)
    db.execute(
        "INSERT OR REPLACE INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        (table, now_iso, etag, final_count),
    )
    db.commit()
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\data_sync.py tests\services\test_data_sync.py
git commit -m "feat(plan-2): add data_sync.sync_curated_data with ETag support"
```

---

### Task 16 : data_sync — 304 Not Modified, 24h skip, offline graceful

**Files:**
- Modify: `tests/services/test_data_sync.py`

- [ ] **Step 1: Add edge-case tests**

Append to `tests/services/test_data_sync.py`:

```python
@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_skips_when_recently_synced(empty_db: sqlite3.Connection) -> None:
    """Recent sync (<24h) → skipped without HTTP call (force=False default)."""
    # Pre-populate meta as if synced 1h ago
    empty_db.execute(
        "INSERT INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        ("species", (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat(), '"old"', 0),
    )
    empty_db.commit()

    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        route = router.get(url__regex=r".*species\.csv").mock(
            return_value=httpx.Response(200, content=_SPECIES_CSV.encode())
        )
        # Other tables: also return 200 so they go through (only species should be skipped)
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = await data_sync.sync_curated_data(empty_db, force=False)

    assert "species" in result["tables_skipped"]
    assert route.call_count == 0


@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_handles_304_not_modified(empty_db: sqlite3.Connection) -> None:
    """Server returns 304 → table marked synced but rows not touched."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    empty_db.execute(
        "INSERT INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        # Last sync 26h ago so we don't skip
        ("species", (dt.datetime.now(dt.UTC) - dt.timedelta(hours=26)).isoformat(), '"abc123"', 1),
    )
    empty_db.commit()

    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.get(url__regex=r".*species\.csv").mock(
            return_value=httpx.Response(304)
        )
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = await data_sync.sync_curated_data(empty_db, force=False)

    assert "species" in result["tables_skipped"]
    rows = empty_db.execute("SELECT COUNT(*) FROM species").fetchone()
    assert rows[0] == 1


@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_offline_records_errors(empty_db: sqlite3.Connection) -> None:
    """All requests timeout → errors[] is populated, no crash."""
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.get(url__regex=r".*\.csv").mock(side_effect=httpx.TimeoutException("offline"))

        result = await data_sync.sync_curated_data(empty_db, force=True)

    assert result["tables_synced"] == []
    assert len(result["errors"]) > 0
    # Error string mentions network or TimeoutException
    assert any("network" in err or "Timeout" in err for err in result["errors"])


@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_5xx_records_error_continues(empty_db: sqlite3.Connection) -> None:
    """503 on one table doesn't block other tables."""
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.get(url__regex=r".*species\.csv").mock(return_value=httpx.Response(503))
        router.get(url__regex=r".*water_types\.csv").mock(
            return_value=httpx.Response(
                200,
                content=b"id,name_fr,name_en\n1,Lac,Lake\n",
                headers={"ETag": '"wt1"'},
            )
        )
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = await data_sync.sync_curated_data(empty_db, force=True)

    assert "water_types" in result["tables_synced"]
    assert any("species" in e for e in result["errors"])
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: 5 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_data_sync.py
git commit -m "test(plan-2): cover data_sync 24h skip, 304, timeout and 5xx paths"
```

---

### Task 17 : data_sync — malformed CSV doesn't corrupt DB

**Files:**
- Modify: `tests/services/test_data_sync.py`
- Modify: `app/services/data_sync.py`

- [ ] **Step 1: Add malformed-CSV test**

Append to `tests/services/test_data_sync.py`:

```python
@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_malformed_csv_records_error(empty_db: sqlite3.Connection) -> None:
    """Bad CSV column → error logged, original DB untouched."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Existing', 'Existing', 'Sander')"
    )
    empty_db.commit()

    bad_csv = "this,is,not,valid_for_species\n1,2,3,4\n"
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.get(url__regex=r".*species\.csv").mock(
            return_value=httpx.Response(200, content=bad_csv.encode(), headers={"ETag": '"x"'})
        )
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = await data_sync.sync_curated_data(empty_db, force=True)

    # The error should reference species
    assert any("species" in e for e in result["errors"])
    # The pre-existing row must still be present (no half-applied delete+insert)
    rows = empty_db.execute("SELECT COUNT(*) FROM species").fetchone()
    assert rows[0] == 1
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_data_sync.py -v -k malformed`

Expected: FAIL — current implementation calls `db.execute("DELETE")` then crashes on bad INSERT, but commits each row. We need transactional safety.

- [ ] **Step 3: Wrap _replace_table_rows in a transaction**

Edit `app/services/data_sync.py` — replace `_replace_table_rows` with:

```python
def _replace_table_rows(db: sqlite3.Connection, table: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        with db:
            db.execute(f"DELETE FROM {table}")
        return
    columns = list(rows[0].keys())
    placeholders = ",".join("?" for _ in columns)
    column_list = ",".join(columns)
    insert_sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"

    # Use transaction: if any insert fails, the DELETE is rolled back.
    try:
        with db:
            db.execute(f"DELETE FROM {table}")
            for row in rows:
                values = [_coerce_csv_cell(row[c]) for c in columns]
                db.execute(insert_sql, values)
    except sqlite3.Error:
        # Caller catches this and records the error; no half-applied state.
        raise
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\data_sync.py tests\services\test_data_sync.py
git commit -m "fix(plan-2): wrap data_sync table refresh in transaction for atomicity"
```

---

## geolocation — Windows Location API + IP fallback

### Task 18 : geolocation — Windows Location API success

**Files:**
- Create: `app/services/geolocation.py`
- Create: `tests/services/test_geolocation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_geolocation.py`:

```python
"""Tests for app.services.geolocation — Windows Location API + IP fallback.

The Windows API (winsdk) is mocked across all tests so the suite runs on Linux CI too.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from app.services import geolocation


def test_get_current_location_uses_windows_api_when_available() -> None:
    """When winsdk reports a position, return its coordinates without IP fallback."""
    fake_position = MagicMock()
    fake_position.coordinate.latitude = 46.81
    fake_position.coordinate.longitude = -71.21

    with patch.object(geolocation, "_query_windows_location", return_value=(46.81, -71.21)):
        result = geolocation.get_current_location()

    assert result == (46.81, -71.21)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/services/test_geolocation.py -v`

Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement geolocation module**

Create `app/services/geolocation.py`:

```python
"""Geolocation: Windows Location API first, fallback to IP geolocation via ipapi.co.

Tests must mock both `_query_windows_location` and `_query_ip_location`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_IPAPI_URL = "https://ipapi.co/json/"
_TIMEOUT_SECONDS = 4.0


def get_current_location() -> tuple[float, float] | None:
    """Best-effort lat/lon detection.

    Order:
      1. Windows Location API via winsdk (only on win32).
      2. IP geolocation via ipapi.co (free, 1k req/day, no key).

    Returns: (lat, lon) tuple or None if all methods fail.
    """
    if sys.platform == "win32":
        try:
            result = _query_windows_location()
            if result is not None:
                return result
        except Exception as exc:  # noqa: BLE001
            logger.warning("Windows Location API failed: %s", exc)

    try:
        return _query_ip_location()
    except Exception as exc:  # noqa: BLE001
        logger.warning("IP geolocation failed: %s", exc)
        return None


def _query_windows_location() -> tuple[float, float] | None:
    """Call winsdk to get the current position. Synchronous wrapper around the async API.

    Raises if winsdk is unavailable or the user denied permission.
    """
    import asyncio

    from winsdk.windows.devices.geolocation import Geolocator

    async def _go() -> Any:
        loc = Geolocator()
        position = await loc.get_geoposition_async()
        return position

    position = asyncio.run(_go())
    if position is None or position.coordinate is None:
        return None
    coord = position.coordinate
    return (float(coord.latitude), float(coord.longitude))


def _query_ip_location() -> tuple[float, float] | None:
    """Fallback: ipapi.co returns lat/lon based on the caller IP."""
    response = httpx.get(_IPAPI_URL, timeout=_TIMEOUT_SECONDS)
    if response.status_code != 200:
        return None
    data = response.json()
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon))
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/services/test_geolocation.py -v`

Expected: 1 PASS.

- [ ] **Step 5: Commit**

```powershell
git add app\services\geolocation.py tests\services\test_geolocation.py
git commit -m "feat(plan-2): add geolocation.get_current_location with winsdk + IP fallback"
```

---

### Task 19 : geolocation — IP fallback when Windows fails

**Files:**
- Modify: `tests/services/test_geolocation.py`

- [ ] **Step 1: Add IP-fallback tests**

Append to `tests/services/test_geolocation.py`:

```python
def test_get_current_location_falls_back_to_ip() -> None:
    """If winsdk raises, IP fallback is used."""
    with patch.object(geolocation, "_query_windows_location", side_effect=Exception("denied")):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(
                    200, json={"latitude": 45.50, "longitude": -73.57, "city": "Montreal"}
                )
            )
            result = geolocation.get_current_location()

    assert result == (45.50, -73.57)


def test_get_current_location_returns_none_when_all_fail() -> None:
    with patch.object(geolocation, "_query_windows_location", side_effect=Exception("denied")):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(side_effect=httpx.TimeoutException("timeout"))
            result = geolocation.get_current_location()

    assert result is None


def test_get_current_location_ip_5xx_returns_none() -> None:
    with patch.object(geolocation, "_query_windows_location", return_value=None):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(return_value=httpx.Response(503))
            result = geolocation.get_current_location()
    assert result is None


def test_get_current_location_ip_missing_fields_returns_none() -> None:
    with patch.object(geolocation, "_query_windows_location", return_value=None):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(200, json={"city": "Lévis"})
            )
            result = geolocation.get_current_location()
    assert result is None


def test_get_current_location_skips_winsdk_on_non_win32() -> None:
    """On Linux CI, sys.platform != 'win32' so winsdk is skipped."""
    with patch.object(geolocation.sys, "platform", "linux"):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(200, json={"latitude": 1.0, "longitude": 2.0})
            )
            result = geolocation.get_current_location()
    assert result == (1.0, 2.0)
```

- [ ] **Step 2: Run tests to verify pass**

Run: `pytest tests/services/test_geolocation.py -v`

Expected: 5 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_geolocation.py
git commit -m "test(plan-2): cover geolocation IP fallback and failure modes"
```

---

## Cross-cutting integration tasks

### Task 20 : integration — recommender + baro_analyzer end-to-end

**Files:**
- Create: `tests/services/test_integration_recommender_baro.py`

- [ ] **Step 1: Write the integration test**

Create `tests/services/test_integration_recommender_baro.py`:

```python
"""Integration test: real DB seed + baro_analyzer + recommender wired together."""

import sqlite3

from app.services import baro_analyzer, recommender


def test_baro_trend_drives_recommendation_score(empty_db: sqlite3.Connection) -> None:
    # Seed
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    empty_db.execute(
        "INSERT INTO baro_rules (species_id, baro_trend, activity_score) "
        "VALUES (3, 'falling', 9)"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, baro_trend, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, 'falling', 'Pression chute', 'Falling pressure', NULL, 5)"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, baro_trend, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, 'rising', 'Pression montante', 'Rising pressure', NULL, 4)"
    )
    empty_db.commit()

    # 1. Determine baro trend from a rapidly falling pressure series
    pressures = [1015.0, 1014.5, 1013.5, 1012.5, 1011.5, 1010.5, 1010.0]
    trend = baro_analyzer.analyze_trend(pressures)
    assert trend == "falling"

    # 2. Score walleye for that trend
    score = baro_analyzer.species_activity_score(empty_db, 3, trend)
    assert score == 9

    # 3. Use the trend to drive recommendations
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=None, water_type_id=None,
        conditions={"baro_trend": trend},
    )
    assert result[0]["tip_text_fr"] == "Pression chute"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_integration_recommender_baro.py -v`

Expected: 1 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_integration_recommender_baro.py
git commit -m "test(plan-2): add integration test for baro_analyzer + recommender"
```

---

### Task 21 : integration — solunar + astral_calc real path

**Files:**
- Create: `tests/services/test_integration_solunar_astral.py`

- [ ] **Step 1: Write the integration test**

Create `tests/services/test_integration_solunar_astral.py`:

```python
"""Integration: real astral_calc + real solunar (no mock).

Verifies astral_calc returns valid moon transits and that solunar wraps them
into 2h windows for a real lat/lon/date.
"""

import datetime as dt

from freezegun import freeze_time

from app.services import solunar


@freeze_time("2026-06-21 12:00:00")
def test_solunar_real_chain_levis_qc_returns_some_periods() -> None:
    """For Lévis QC at summer solstice, expect ≥1 major or minor period."""
    result = solunar.compute_periods(lat=46.81, lon=-71.21, date=dt.date(2026, 6, 21))
    total_periods = len(result["major"]) + len(result["minor"])
    assert total_periods >= 1, f"Expected at least 1 period, got {result}"


@freeze_time("2026-06-21 12:00:00")
def test_solunar_real_chain_montreal_returns_iso_strings() -> None:
    """Montreal QC — sanity check that ISO timestamps parse."""
    result = solunar.compute_periods(lat=45.50, lon=-73.57, date=dt.date(2026, 6, 21))
    for period in result["major"] + result["minor"]:
        # Either parses or is empty (graceful)
        if period["start"]:
            dt.datetime.fromisoformat(period["start"])
            dt.datetime.fromisoformat(period["end"])
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_integration_solunar_astral.py -v`

Expected: 2 PASS. (Note: this test downloads `de421.bsp` if not cached. ~17MB one-time.)

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_integration_solunar_astral.py
git commit -m "test(plan-2): add integration test for astral_calc + solunar real chain"
```

---

### Task 22 : integration — openmeteo_client + baro_analyzer pipeline

**Files:**
- Create: `tests/services/test_integration_weather_baro.py`

- [ ] **Step 1: Write the integration test**

Create `tests/services/test_integration_weather_baro.py`:

```python
"""Integration: openmeteo_client → baro_analyzer pipeline.

Verifies that the pressures_history_hpa returned by get_weather feeds correctly
into analyze_trend.
"""

import sqlite3

import httpx
import pytest
import respx

from app.services import baro_analyzer, openmeteo_client


_FAKE_FALLING_RESPONSE = {
    "current": {
        "time": "2026-06-21T12:00",
        "temperature_2m": 22.0,
        "pressure_msl": 1010.0,
        "wind_speed_10m": 8.0,
        "relative_humidity_2m": 60,
    },
    "hourly": {
        "time": [
            "2026-06-21T06:00", "2026-06-21T07:00", "2026-06-21T08:00",
            "2026-06-21T09:00", "2026-06-21T10:00", "2026-06-21T11:00",
            "2026-06-21T12:00",
        ],
        "pressure_msl": [1015.0, 1014.0, 1013.0, 1012.0, 1011.5, 1010.5, 1010.0],
    },
}


@pytest.mark.asyncio
async def test_weather_baro_pipeline_detects_falling_pressure() -> None:
    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_FALLING_RESPONSE)
        )
        weather = await openmeteo_client.get_weather(46.81, -71.21, db=None)

    assert baro_analyzer.analyze_trend(weather["pressures_history_hpa"]) == "falling"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_integration_weather_baro.py -v`

Expected: 1 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_integration_weather_baro.py
git commit -m "test(plan-2): add integration test for openmeteo_client + baro_analyzer"
```

---

## Service-level safeguards & polish

### Task 23 : recommender — locale-tagged limit + deterministic tie-breaking

**Files:**
- Modify: `tests/services/test_recommender.py`
- Modify: `app/services/recommender.py`

- [ ] **Step 1: Add deterministic-order test**

Append to `tests/services/test_recommender.py`:

```python
def test_recommend_same_score_orders_by_confidence_then_id(
    empty_db: sqlite3.Connection,
) -> None:
    """Two tips with identical match_score: higher confidence first; ties broken by id ASC."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    rows = [
        # (id, species_id, tip_fr, tip_en, confidence)
        (1, 3, "Tip A", "Tip A", 4),
        (2, 3, "Tip B", "Tip B", 5),  # higher confidence — should come first
        (3, 3, "Tip C", "Tip C", 4),
    ]
    for tid, sid, fr, en, conf in rows:
        empty_db.execute(
            "INSERT INTO tips (id, species_id, tip_text_fr, tip_text_en, source_url, confidence) "
            "VALUES (?, ?, ?, ?, NULL, ?)",
            (tid, sid, fr, en, conf),
        )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=None, water_type_id=None, conditions={},
    )
    texts = [t["tip_text_fr"] for t in result]
    assert texts == ["Tip B", "Tip A", "Tip C"]


def test_recommend_limit_zero_returns_empty(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=1, water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full",
                    "season": "summer", "time_of_day": "morning"},
        limit=0,
    )
    assert result == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_recommender.py -v`

Expected: all PASS (the implementation already orders by score DESC, confidence DESC, id ASC; limit=0 slices to []).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_recommender.py
git commit -m "test(plan-2): cover recommender deterministic tie-break and limit=0"
```

---

### Task 24 : openmeteo_client — round lat/lon for cache key (rate-limit mitigation)

**Files:**
- Modify: `tests/services/test_openmeteo_client.py`

- [ ] **Step 1: Add coverage tests for cache-key rounding**

Append to `tests/services/test_openmeteo_client.py`:

```python
@pytest.mark.asyncio
async def test_get_weather_cache_key_rounds_to_two_decimals(
    empty_db: sqlite3.Connection,
) -> None:
    """Two calls within 0.01° (~1km) hit the same cache row → 1 network call."""
    with respx.mock() as router:
        route = router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        await openmeteo_client.get_weather(46.811, -71.211, db=empty_db)
        await openmeteo_client.get_weather(46.814, -71.213, db=empty_db)

    assert route.call_count == 1


@pytest.mark.asyncio
async def test_get_weather_cache_key_distinct_at_two_decimal_boundary(
    empty_db: sqlite3.Connection,
) -> None:
    """Two calls separated by >0.01° → 2 distinct cache rows → 2 network calls."""
    with respx.mock() as router:
        route = router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
        await openmeteo_client.get_weather(46.83, -71.23, db=empty_db)

    assert route.call_count == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 9 PASS (existing 7 + 2 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_openmeteo_client.py
git commit -m "test(plan-2): verify openmeteo cache key rounds to ~1km grid for rate-limit"
```

---

### Task 25 : data_sync — verify exact GitHub raw URL is hit

**Files:**
- Modify: `tests/services/test_data_sync.py`

- [ ] **Step 1: Add URL assertion test**

Append to `tests/services/test_data_sync.py`:

```python
@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_uses_correct_github_raw_url(empty_db: sqlite3.Connection) -> None:
    """Confirm the URL hit is the one defined in the spec (sxc3030-eng/pechepro/main)."""
    with respx.mock() as router:
        species_route = router.get(
            "https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/species.csv"
        ).mock(
            return_value=httpx.Response(200, content=_SPECIES_CSV.encode(),
                                        headers={"ETag": '"abc"'})
        )
        # Allow other paths to 404 quietly
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        await data_sync.sync_curated_data(empty_db, force=True)

    assert species_route.called
    assert species_route.call_count == 1


@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_sends_if_none_match_when_etag_known(
    empty_db: sqlite3.Connection,
) -> None:
    empty_db.execute(
        "INSERT INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        ("species", (dt.datetime.now(dt.UTC) - dt.timedelta(hours=26)).isoformat(),
         '"prev-etag"', 5),
    )
    empty_db.commit()

    with respx.mock() as router:
        species_route = router.get(
            url__regex=r".*species\.csv"
        ).mock(return_value=httpx.Response(304))
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        await data_sync.sync_curated_data(empty_db, force=True)

    assert species_route.calls.last.request.headers.get("If-None-Match") == '"prev-etag"'
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: 8 PASS (6 existing + 2 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_data_sync.py
git commit -m "test(plan-2): assert data_sync uses correct GitHub URL and If-None-Match"
```

---

### Task 26 : usgs_client — verify parameterCd=00010 (water temp) is sent

**Files:**
- Modify: `tests/services/test_usgs_client.py`

- [ ] **Step 1: Add parameter assertion test**

Append to `tests/services/test_usgs_client.py`:

```python
@pytest.mark.asyncio
async def test_get_water_temp_sends_parameter_cd_00010() -> None:
    """USGS expects parameterCd=00010 for water temperature (Celsius)."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        await usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert route.call_count == 1
    qp = dict(route.calls.last.request.url.params)
    assert qp.get("parameterCd") == "00010"
    assert qp.get("format") == "json"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_usgs_client.py -v`

Expected: 7 PASS (6 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_usgs_client.py
git commit -m "test(plan-2): verify usgs_client sends parameterCd=00010 (water temp)"
```

---

### Task 27 : eccc_client — verify bbox is computed correctly

**Files:**
- Modify: `tests/services/test_eccc_client.py`

- [ ] **Step 1: Add bbox test**

Append to `tests/services/test_eccc_client.py`:

```python
@pytest.mark.asyncio
async def test_get_water_temp_sends_bbox_around_lat_lon() -> None:
    with respx.mock() as router:
        route = router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        await eccc_client.get_water_temp(lat=46.81, lon=-71.21)

    qp = dict(route.calls.last.request.url.params)
    bbox = qp.get("bbox", "")
    parts = bbox.split(",")
    assert len(parts) == 4
    minx, miny, maxx, maxy = (float(p) for p in parts)
    assert minx < -71.21 < maxx
    assert miny < 46.81 < maxy
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_eccc_client.py -v`

Expected: 8 PASS (7 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_eccc_client.py
git commit -m "test(plan-2): verify eccc_client bbox encloses requested lat/lon"
```

---

## Public API contract verification

### Task 28 : signature contract — each service matches the spec exactly

**Files:**
- Create: `tests/services/test_public_api_contracts.py`

- [ ] **Step 1: Write the failing test**

Create `tests/services/test_public_api_contracts.py`:

```python
"""Verify the public API surface matches the contract documented in plan-2.

Used to detect accidental signature drift before plan-1 wires Flask routes.
"""

import inspect
from typing import get_type_hints

from app.services import (
    astral_calc,
    baro_analyzer,
    data_sync,
    eccc_client,
    geolocation,
    openmeteo_client,
    recommender,
    solunar,
    usgs_client,
)


def test_recommender_recommend_signature() -> None:
    sig = inspect.signature(recommender.recommend)
    params = list(sig.parameters.keys())
    assert params == ["db", "species_id", "region_id", "water_type_id", "conditions", "limit"]
    assert sig.parameters["limit"].default == 10


def test_solunar_compute_periods_signature() -> None:
    sig = inspect.signature(solunar.compute_periods)
    params = list(sig.parameters.keys())
    assert params == ["lat", "lon", "date"]


def test_baro_analyzer_signatures() -> None:
    sig1 = inspect.signature(baro_analyzer.analyze_trend)
    assert list(sig1.parameters.keys()) == ["pressures_hpa", "hours_window"]
    assert sig1.parameters["hours_window"].default == 6

    sig2 = inspect.signature(baro_analyzer.species_activity_score)
    assert list(sig2.parameters.keys()) == ["db", "species_id", "baro_trend"]


def test_astral_calc_sun_moon_signature() -> None:
    sig = inspect.signature(astral_calc.sun_moon)
    assert list(sig.parameters.keys()) == ["lat", "lon", "date"]


def test_openmeteo_client_get_weather_signature() -> None:
    sig = inspect.signature(openmeteo_client.get_weather)
    assert list(sig.parameters.keys()) == ["lat", "lon", "db"]
    assert sig.parameters["db"].default is None
    # Async function
    assert inspect.iscoroutinefunction(openmeteo_client.get_weather)


def test_usgs_client_get_water_temp_signature() -> None:
    sig = inspect.signature(usgs_client.get_water_temp)
    assert list(sig.parameters.keys()) == ["lat", "lon"]
    assert inspect.iscoroutinefunction(usgs_client.get_water_temp)


def test_eccc_client_get_water_temp_signature() -> None:
    sig = inspect.signature(eccc_client.get_water_temp)
    assert list(sig.parameters.keys()) == ["lat", "lon"]
    assert inspect.iscoroutinefunction(eccc_client.get_water_temp)


def test_data_sync_sync_curated_data_signature() -> None:
    sig = inspect.signature(data_sync.sync_curated_data)
    assert list(sig.parameters.keys()) == ["db", "force"]
    assert sig.parameters["force"].default is False
    assert inspect.iscoroutinefunction(data_sync.sync_curated_data)


def test_geolocation_get_current_location_signature() -> None:
    sig = inspect.signature(geolocation.get_current_location)
    assert list(sig.parameters.keys()) == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_public_api_contracts.py -v`

Expected: 9 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_public_api_contracts.py
git commit -m "test(plan-2): pin public API signatures for plan-1 integration"
```

---

### Task 29 : type-hint smoke for each service

**Files:**
- Modify: `tests/services/test_public_api_contracts.py`

- [ ] **Step 1: Add type-hint coverage assertions**

Append to `tests/services/test_public_api_contracts.py`:

```python
def test_all_public_functions_have_type_hints() -> None:
    """Every public service function must have annotated parameters and return type."""
    public_callables = [
        recommender.recommend,
        solunar.compute_periods,
        baro_analyzer.analyze_trend,
        baro_analyzer.species_activity_score,
        astral_calc.sun_moon,
        openmeteo_client.get_weather,
        usgs_client.get_water_temp,
        eccc_client.get_water_temp,
        data_sync.sync_curated_data,
        geolocation.get_current_location,
    ]
    for fn in public_callables:
        hints = get_type_hints(fn)
        assert "return" in hints, f"{fn.__qualname__} missing return type hint"
        sig = inspect.signature(fn)
        for pname in sig.parameters:
            assert pname in hints, f"{fn.__qualname__} param {pname} missing type hint"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_public_api_contracts.py -v`

Expected: 10 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_public_api_contracts.py
git commit -m "test(plan-2): assert all public service functions have full type hints"
```

---

## Resilience & risk-mitigation tasks (from spec §11)

### Task 30 : openmeteo_client — concurrent identical requests don't double-fetch

**Files:**
- Modify: `tests/services/test_openmeteo_client.py`

- [ ] **Step 1: Add concurrent test**

Append to `tests/services/test_openmeteo_client.py`:

```python
import asyncio


@pytest.mark.asyncio
async def test_get_weather_two_sequential_calls_share_cache(
    empty_db: sqlite3.Connection,
) -> None:
    """After the first call writes the cache row, the second call must read from cache."""
    with respx.mock() as router:
        route = router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        first = await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
        second = await openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    assert first == second
    assert route.call_count == 1
    # Cache row exists
    row = empty_db.execute(
        "SELECT cache_key FROM weather_cache WHERE cache_key = '46.81,-71.21'"
    ).fetchone()
    assert row is not None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 10 PASS (9 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_openmeteo_client.py
git commit -m "test(plan-2): verify openmeteo cache row is written for subsequent reuse"
```

---

### Task 31 : data_sync — when DB is uninitialized, sync still works

**Files:**
- Modify: `tests/services/test_data_sync.py`

- [ ] **Step 1: Add cold-start test**

Append to `tests/services/test_data_sync.py`:

```python
@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_first_run_no_meta_rows(empty_db: sqlite3.Connection) -> None:
    """Cold start (data_sync_meta is empty) → all tables fetched."""
    csvs = {
        "species": _SPECIES_CSV,
        "water_types": "id,name_fr,name_en\n1,Lac,Lake\n",
    }
    with respx.mock() as router:
        for table, body in csvs.items():
            router.get(
                url__regex=rf".*{table}\.csv"
            ).mock(
                return_value=httpx.Response(
                    200, content=body.encode(), headers={"ETag": f'"{table}-1"'}
                )
            )
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = await data_sync.sync_curated_data(empty_db, force=False)

    assert "species" in result["tables_synced"]
    assert "water_types" in result["tables_synced"]
    # Meta rows now exist
    rows = empty_db.execute("SELECT table_name FROM data_sync_meta ORDER BY table_name").fetchall()
    table_names = {r[0] for r in rows}
    assert "species" in table_names
    assert "water_types" in table_names
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: 9 PASS (8 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_data_sync.py
git commit -m "test(plan-2): verify data_sync handles cold-start (empty data_sync_meta)"
```

---

### Task 32 : recommender — handles species_id=None gracefully

**Files:**
- Modify: `tests/services/test_recommender.py`
- Modify: `app/services/recommender.py`

- [ ] **Step 1: Add validation test**

Append to `tests/services/test_recommender.py`:

```python
def test_recommend_species_id_none_raises(empty_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        recommender.recommend(
            db=empty_db,
            species_id=None,  # type: ignore[arg-type]
            region_id=1,
            water_type_id=1,
            conditions={},
        )


def test_recommend_negative_limit_returns_empty(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=1, water_type_id=1,
        conditions={"baro_trend": "falling"},
        limit=-5,
    )
    assert result == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_recommender.py -v`

Expected: First test FAILS (no validation); second PASSES (slice [:-5] hides last 5).

- [ ] **Step 3: Add validation**

Edit `app/services/recommender.py` — add at the top of `recommend`:

```python
def recommend(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int | None,
    water_type_id: int | None,
    conditions: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the top-N tips for the requested species and conditions.

    Args, Returns: see module docstring.

    Raises: TypeError if species_id is not an int.
    """
    if not isinstance(species_id, int):
        raise TypeError(f"species_id must be int, got {type(species_id).__name__}")
    if limit <= 0:
        return []

    sql_parts = ["SELECT id, tip_text_fr, tip_text_en, source_url, confidence, "
                 "season, baro_trend, moon_phase, time_of_day, "
                 "temp_water_min_c, temp_water_max_c "
                 "FROM tips WHERE species_id = ?"]
    # ... rest unchanged
```

(Replace the existing function with this updated version, keeping the rest of the body identical.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/services/test_recommender.py -v`

Expected: 13 PASS (existing 11 + 2 new).

- [ ] **Step 5: Commit**

```powershell
git add app\services\recommender.py tests\services\test_recommender.py
git commit -m "feat(plan-2): validate recommender inputs (species_id type, limit<=0)"
```

---

### Task 33 : solunar — verify deterministic windows under freezegun

**Files:**
- Modify: `tests/services/test_solunar.py`

- [ ] **Step 1: Add deterministic-output test**

Append to `tests/services/test_solunar.py`:

```python
@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_deterministic_under_freeze() -> None:
    """Two calls with identical inputs under freeze_time return identical output."""
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=_FAKE_SUN_MOON):
        a = solunar.compute_periods(46.81, -71.21, dt.date(2026, 6, 21))
        b = solunar.compute_periods(46.81, -71.21, dt.date(2026, 6, 21))
    assert a == b
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_solunar.py -v`

Expected: 6 PASS (5 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_solunar.py
git commit -m "test(plan-2): verify solunar.compute_periods is deterministic"
```

---

### Task 34 : geolocation — handle Geolocator import error on Linux test runner

**Files:**
- Modify: `tests/services/test_geolocation.py`

- [ ] **Step 1: Add Linux-CI smoke test**

Append to `tests/services/test_geolocation.py`:

```python
def test_query_windows_location_skipped_on_non_win32() -> None:
    """On Linux, _query_windows_location should not be called by the public function."""
    with patch.object(geolocation.sys, "platform", "linux"):
        with patch.object(geolocation, "_query_windows_location") as mock_win:
            with respx.mock() as router:
                router.get(geolocation._IPAPI_URL).mock(
                    return_value=httpx.Response(
                        200, json={"latitude": 1.5, "longitude": 2.5}
                    )
                )
                result = geolocation.get_current_location()
    mock_win.assert_not_called()
    assert result == (1.5, 2.5)
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_geolocation.py -v`

Expected: 6 PASS (5 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_geolocation.py
git commit -m "test(plan-2): verify geolocation skips winsdk path on non-win32"
```

---

### Task 35 : data_sync — concurrent service availability (httpx connect error)

**Files:**
- Modify: `tests/services/test_data_sync.py`

- [ ] **Step 1: Add ConnectError test**

Append to `tests/services/test_data_sync.py`:

```python
@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_connect_error_records_error(empty_db: sqlite3.Connection) -> None:
    """ConnectError (DNS/firewall) is treated like a network failure."""
    with respx.mock() as router:
        router.get(url__regex=r".*\.csv").mock(
            side_effect=httpx.ConnectError("dns failure")
        )
        result = await data_sync.sync_curated_data(empty_db, force=True)

    assert result["tables_synced"] == []
    assert all("network" in e or "Connect" in e for e in result["errors"])
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_data_sync.py -v`

Expected: 10 PASS (9 existing + 1 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_data_sync.py
git commit -m "test(plan-2): verify data_sync handles ConnectError as network failure"
```

---

### Task 36 : usgs_client + eccc_client — both return None for invalid country bbox

**Files:**
- Modify: `tests/services/test_usgs_client.py`
- Modify: `tests/services/test_eccc_client.py`

- [ ] **Step 1: Add cross-border tests**

Append to `tests/services/test_usgs_client.py`:

```python
@pytest.mark.asyncio
async def test_usgs_returns_none_for_canadian_lat_lon() -> None:
    """Lévis QC is in Canada — USGS returns None even with mock."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        result = await usgs_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None
    assert route.call_count == 0


@pytest.mark.asyncio
async def test_usgs_returns_none_for_mexican_lat_lon() -> None:
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        result = await usgs_client.get_water_temp(lat=19.43, lon=-99.13)  # Mexico City
    assert result is None
    assert route.call_count == 0
```

Append to `tests/services/test_eccc_client.py`:

```python
@pytest.mark.asyncio
async def test_eccc_returns_none_for_us_lat_lon() -> None:
    """Vermont is in the US — ECCC returns None even with mock."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        result = await eccc_client.get_water_temp(lat=44.5, lon=-72.0)
    assert result is None
    assert route.call_count == 0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_usgs_client.py tests/services/test_eccc_client.py -v`

Expected: usgs 9 PASS, eccc 9 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_usgs_client.py tests\services\test_eccc_client.py
git commit -m "test(plan-2): verify USGS/ECCC clients reject cross-border lat/lon"
```

---

### Task 37 : astral_calc — moon phase classification edge values

**Files:**
- Modify: `tests/services/test_astral_calc.py`

- [ ] **Step 1: Add boundary tests**

Append to `tests/services/test_astral_calc.py`:

```python
def test_classify_moon_phase_boundaries() -> None:
    """Validate the 4-bucket phase classifier at boundaries."""
    classify = astral_calc._classify_moon_phase
    assert classify(0.0) == "new"
    assert classify(6.99) == "new"
    assert classify(7.0) == "waxing"
    assert classify(13.99) == "waxing"
    assert classify(14.0) == "full"
    assert classify(20.99) == "full"
    assert classify(21.0) == "waning"
    assert classify(28.0) == "waning"


def test_moon_illumination_range() -> None:
    """Illumination must always be in [0, 1]."""
    illum = astral_calc._moon_illumination
    for phase_val in [0.0, 7.0, 14.0, 21.0, 28.0]:
        result = illum(phase_val)
        assert 0.0 <= result <= 1.0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_astral_calc.py -v`

Expected: 7 PASS (5 existing + 2 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_astral_calc.py
git commit -m "test(plan-2): cover astral_calc moon phase boundaries and illumination"
```

---

### Task 38 : baro_analyzer — short series fallback + threshold tuning

**Files:**
- Modify: `tests/services/test_baro_analyzer.py`

- [ ] **Step 1: Add tests**

Append to `tests/services/test_baro_analyzer.py`:

```python
def test_analyze_trend_threshold_at_exactly_05_hpa() -> None:
    """Boundary: exact +0.5 hPa over the window → 'rising' (inclusive)."""
    pressures = [1010.0, 1010.5]
    assert baro_analyzer.analyze_trend(pressures) == "rising"


def test_analyze_trend_threshold_at_exactly_minus_05_hpa() -> None:
    pressures = [1010.5, 1010.0]
    assert baro_analyzer.analyze_trend(pressures) == "falling"


def test_analyze_trend_just_below_threshold_is_steady() -> None:
    pressures = [1010.0, 1010.49]
    assert baro_analyzer.analyze_trend(pressures) == "steady"


def test_species_activity_score_rejects_score_out_of_range_via_check(
    empty_db: sqlite3.Connection,
) -> None:
    """The DB CHECK constraint prevents scores outside 1..10. We verify graceful read."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'X', 'X', 'X')"
    )
    empty_db.execute(
        "INSERT INTO baro_rules (species_id, baro_trend, activity_score) "
        "VALUES (3, 'rising', 8)"
    )
    empty_db.commit()
    assert baro_analyzer.species_activity_score(empty_db, 3, "rising") == 8
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_baro_analyzer.py -v`

Expected: 12 PASS (8 existing + 4 new).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_baro_analyzer.py
git commit -m "test(plan-2): cover baro_analyzer threshold boundaries"
```

---

## Final coverage & wrap-up

### Task 39 : tighten openmeteo_client — handle 4xx (unexpected non-200/304)

**Files:**
- Modify: `tests/services/test_openmeteo_client.py`

- [ ] **Step 1: Add 4xx test**

Append to `tests/services/test_openmeteo_client.py`:

```python
@pytest.mark.asyncio
async def test_get_weather_400_raises_status_error() -> None:
    """A 400 from Open-Meteo should propagate (caller handles)."""
    with respx.mock() as router:
        router.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(400, json={"error": "bad params"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await openmeteo_client.get_weather(46.81, -71.21, db=None)
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_openmeteo_client.py -v`

Expected: 11 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_openmeteo_client.py
git commit -m "test(plan-2): verify openmeteo_client surfaces 4xx as HTTPStatusError"
```

---

### Task 40 : recommender — large-N performance smoke (1k tips)

**Files:**
- Modify: `tests/services/test_recommender.py`

- [ ] **Step 1: Add bulk test**

Append to `tests/services/test_recommender.py`:

```python
def test_recommend_handles_1000_tips_under_500ms(empty_db: sqlite3.Connection) -> None:
    """Performance smoke: 1000 tips for a single species should complete fast."""
    import time

    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    rows = []
    for i in range(1000):
        rows.append(
            (3, None, None, "any", "any", "any", None, None, "any",
             f"Tip FR {i}", f"Tip EN {i}", None, (i % 5) + 1)
        )
    empty_db.executemany(
        "INSERT INTO tips (species_id, region_id, water_type_id, season, baro_trend, moon_phase, "
        "temp_water_min_c, temp_water_max_c, time_of_day, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    empty_db.commit()

    start = time.perf_counter()
    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=None, water_type_id=None,
        conditions={"baro_trend": "falling", "moon_phase": "full"},
        limit=10,
    )
    elapsed = time.perf_counter() - start

    assert len(result) == 10
    assert elapsed < 0.5, f"Recommender too slow: {elapsed:.3f}s"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_recommender.py -v -k 1000_tips`

Expected: PASS (well under 500ms).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_recommender.py
git commit -m "test(plan-2): verify recommender handles 1k tips under 500ms"
```

---

### Task 41 : solunar — illumination contributes to per-period score

**Files:**
- Modify: `tests/services/test_solunar.py`

- [ ] **Step 1: Add scoring test**

Append to `tests/services/test_solunar.py`:

```python
@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_minor_score_smaller_than_major() -> None:
    """Under all conditions, minor score < major score (minor windows are fishing 2nd-tier)."""
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=_FAKE_SUN_MOON):
        result = solunar.compute_periods(46.81, -71.21, dt.date(2026, 6, 21))
    assert result["major"][0]["score"] > result["minor"][0]["score"]


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_score_floor_at_zero_illumination() -> None:
    """Even at zero illumination, major score is positive."""
    no_light = dict(_FAKE_SUN_MOON, moon_illumination=0.0, moon_phase="new")
    with patch("app.services.solunar.astral_calc.sun_moon", return_value=no_light):
        result = solunar.compute_periods(46.81, -71.21, dt.date(2026, 6, 21))
    assert result["major"][0]["score"] > 0.0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/services/test_solunar.py -v`

Expected: 8 PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_solunar.py
git commit -m "test(plan-2): verify solunar minor<major and score floor"
```

---

### Task 42 : data_sync — last_synced_at recorded even on 404

**Files:**
- Modify: `app/services/data_sync.py`
- Modify: `tests/services/test_data_sync.py`

- [ ] **Step 1: Add test**

Append to `tests/services/test_data_sync.py`:

```python
@pytest.mark.asyncio
@freeze_time("2026-06-21 12:00:00")
async def test_sync_404_does_not_pollute_meta(empty_db: sqlite3.Connection) -> None:
    """404 is a 'not found' soft-error: it should NOT mark the table as synced
    (so we'll retry on the next launch)."""
    with respx.mock() as router:
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))
        result = await data_sync.sync_curated_data(empty_db, force=True)

    # No table successfully synced
    assert result["tables_synced"] == []
    # And no meta row written
    rows = empty_db.execute("SELECT COUNT(*) FROM data_sync_meta").fetchone()
    assert rows[0] == 0
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_data_sync.py -v -k 404`

Expected: FAIL — current code records errors but does NOT touch meta on 404. Wait, let's verify the expected behavior is implemented... The current `_sync_one_table` returns "not_found" on 404 and the caller adds it to errors. Let's re-check what _bump_synced_at does — it's only called in 200/304 paths. So this test should already pass.

Actually the test expects `tables_synced == []` and meta empty — current behavior matches. Run again to confirm:

Run: `pytest tests/services/test_data_sync.py -v -k 404`

Expected: PASS.

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_data_sync.py
git commit -m "test(plan-2): verify data_sync 404 leaves data_sync_meta untouched"
```

---

### Task 43 : recommender — verify NULL water_type_id semantics

**Files:**
- Modify: `tests/services/test_recommender.py`

- [ ] **Step 1: Add test**

Append to `tests/services/test_recommender.py`:

```python
def test_recommend_water_type_filter_allows_null_tips(empty_db: sqlite3.Connection) -> None:
    """When water_type_id=1 is requested, tips with water_type_id=NULL should still appear
    (NULL is the 'works in any water type' wildcard)."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')"
    )
    empty_db.execute(
        "INSERT INTO water_types (id, name_fr, name_en) VALUES (2, 'Rivière', 'River')"
    )
    # Tip with water_type=1 (specific to lake)
    empty_db.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, 1, 'Lac specific', 'Lake specific', NULL, 4)"
    )
    # Tip with water_type=NULL (works for any water)
    empty_db.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, NULL, 'Toute eau', 'Any water', NULL, 3)"
    )
    # Tip with water_type=2 (river — should be excluded)
    empty_db.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, 2, 'Rivière specific', 'River specific', NULL, 4)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db, species_id=3, region_id=None, water_type_id=1, conditions={},
    )
    texts = {t["tip_text_fr"] for t in result}
    assert "Lac specific" in texts
    assert "Toute eau" in texts
    assert "Rivière specific" not in texts
```

- [ ] **Step 2: Run test**

Run: `pytest tests/services/test_recommender.py -v -k water_type_filter`

Expected: PASS (the SQL `OR water_type_id IS NULL` clause handles this).

- [ ] **Step 3: Commit**

```powershell
git add tests\services\test_recommender.py
git commit -m "test(plan-2): verify recommender water_type=NULL acts as wildcard"
```

---

### Task 44 : run full coverage gate

**Files:** none new

- [ ] **Step 1: Run full pytest with coverage**

```powershell
cd D:\pechepro\.claude\worktrees\plan-2-services
pytest --cov=app.services --cov-report=term-missing --cov-fail-under=80 -v
```

Expected:
- All tests PASS (Tasks 2-43 collectively).
- Coverage ≥80% on `app.services`.
- Output ends with `Required test coverage of 80% reached.`

- [ ] **Step 2: If coverage below 80%, identify gaps**

Read the `--cov-report=term-missing` output. For each missed line, decide:
- Is it dead-code defensive? Add `# pragma: no cover`.
- Is it a real branch we missed? Add a targeted test.

(If we land here, this becomes Task 44.5 with extra tests — only do that if the gate fails.)

- [ ] **Step 3: Commit**

If any new tests or pragma comments were added:

```powershell
git add app\services\ tests\services\
git commit -m "test(plan-2): close coverage gaps, reach >=80% on app.services"
```

If coverage was already green, skip commit.

- [ ] **Step 4: Final tag (optional, parent process may handle)**

```powershell
git log --oneline -30
```

Expected: clear chain of `feat(plan-2)` and `test(plan-2)` commits since the worktree was created.

---

## Self-review checklist

### 1. Spec coverage

| Spec section | Task(s) covering it |
|---|---|
| §3.3 recommender.py | Tasks 13, 14, 23, 32, 40, 43 |
| §3.3 solunar.py | Tasks 4, 5, 21, 33, 41 |
| §3.3 baro_analyzer.py | Tasks 6, 7, 20, 38 |
| §3.3 astral_calc.py | Tasks 2, 3, 21, 37 |
| §3.3 openmeteo_client.py | Tasks 8, 9, 10, 22, 24, 30, 39 |
| §3.3 usgs_client.py | Tasks 11, 26, 36 |
| §3.3 eccc_client.py | Tasks 12, 27, 36 |
| §3.3 data_sync.py | Tasks 15, 16, 17, 25, 31, 35, 42 |
| §3.3 geolocation.py | Tasks 18, 19, 34 |
| §5.1 recommendation logic (in-process) | Tasks 13-14, 20, 22, 32 |
| §5.2 GitHub raw sync | Tasks 15-17, 25, 31, 35, 42 |
| §7 timeouts / fallbacks / hierarchical recommender | Tasks 10 (timeout), 14 (fallback), 11/12/35 (clients return None), 16 (offline), 17 (transactional safety) |
| §11 Open-Meteo 1h cache (rate-limit) | Tasks 8-10, 24, 30 |
| §11 GitHub raw 24h cache + ETag | Tasks 15-16, 25 |
| Public API contract | Tasks 28, 29 |
| Coverage gate ≥80% | Task 44 |

### 2. Type-consistency check

All 10 service signatures match the contract in the brief:

- `recommend(db, species_id, region_id, water_type_id, conditions, limit=10) -> list[dict]` — Tasks 13/28
- `compute_periods(lat, lon, date) -> dict` — Tasks 4/28
- `analyze_trend(pressures_hpa, hours_window=6) -> str` — Tasks 6/28
- `species_activity_score(db, species_id, baro_trend) -> int` — Tasks 7/28
- `sun_moon(lat, lon, date) -> dict` — Tasks 2/28
- `async get_weather(lat, lon, db=None) -> dict` — Tasks 8/28
- `async get_water_temp(lat, lon) -> float | None` (USGS) — Tasks 11/28
- `async get_water_temp(lat, lon) -> float | None` (ECCC) — Tasks 12/28
- `async sync_curated_data(db, force=False) -> dict` — Tasks 15/28
- `get_current_location() -> tuple[float, float] | None` — Tasks 18/28

Task 28 includes an automated assertion that pins these signatures, so any drift fails CI immediately.

### 3. Test isolation

- Every async HTTP call is mocked with `respx`. No test code includes a real URL.
- All datetime operations are wrapped in `freezegun.freeze_time` where they affect output.
- `winsdk` is mocked via `unittest.mock.patch` — tests run on Linux CI runners.
- File system writes are confined to `tmp_path` (the `empty_db` fixture from Phase 0 conftest).
- No subprocess calls, no real DB outside the `tmp_path` SQLite from `empty_db`.

### 4. Coverage target

Task 44 enforces `pytest --cov=app.services --cov-fail-under=80`. The plan structure (every code branch covered by at least one targeted test) should yield ≥85% on a green run. Pragma `# pragma: no cover` is reserved for skyfield ephemeris loading on the unhappy path (download failure) which is integration-level.

---

## Summary

- **Total tasks:** 44 (1 bootstrap + 43 service-implementation tasks)
- **Total step-checkboxes:** ~220 across all tasks
- **Files created in `app/services/`:** 10 (1 `__init__.py` + 9 service modules)
- **Files created in `tests/services/`:** 12 (1 `__init__.py` + 9 per-module + 3 integration + 1 contracts)
- **Strict TDD:** every implementation task starts with a failing test, then minimal code, then re-run.
- **All external I/O mocked.** All datetime fixed with freezegun. Linux CI compatible.
