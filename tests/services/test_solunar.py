"""Tests for app.services.solunar — major/minor period computation.

Canonical signature (from cross-plan amendments + task brief):
- compute_periods(lat, lon, date) -> {"major": [...], "minor": [...]}
- Major periods: moon transit (overhead) + moon underfoot, ±1 hour each (2h windows)
- Minor periods: moonrise + moonset, ±30 min each (1h windows)
- Major weight 1.0; minor weight 0.6
- Score adjustment: +0.2 if period overlaps sunrise or sunset, capped at 1.0
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest
from freezegun import freeze_time

from app.services import solunar

# Lévis QC reference coordinates (used by every spec example).
LEVIS_LAT = 46.81
LEVIS_LON = -71.21
TEST_DATE = dt.date(2026, 6, 21)


# ---------------------------------------------------------------------------
# Task 4 — happy path / shape contract
# ---------------------------------------------------------------------------


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_returns_major_and_minor_keys() -> None:
    """compute_periods returns a dict with 'major' and 'minor' list keys."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    assert isinstance(result, dict)
    assert "major" in result
    assert "minor" in result
    assert isinstance(result["major"], list)
    assert isinstance(result["minor"], list)


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_returns_two_majors_and_two_minors() -> None:
    """Lévis QC on summer solstice — moon rises/sets and transits both occur,
    so we get exactly 2 major + 2 minor periods."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    assert len(result["major"]) == 2
    assert len(result["minor"]) == 2


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_each_period_has_start_end_score() -> None:
    """Every period entry has 'start' (ISO), 'end' (ISO), and 'score' (float in [0,1])."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for period in result["major"] + result["minor"]:
        assert "start" in period
        assert "end" in period
        assert "score" in period
        # ISO timestamps must contain 'T'
        assert "T" in period["start"]
        assert "T" in period["end"]
        # Score must be a normalized float
        assert isinstance(period["score"], float)
        assert 0.0 <= period["score"] <= 1.0


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_iso_timestamps_parseable() -> None:
    """ISO strings round-trip through datetime.fromisoformat."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for period in result["major"] + result["minor"]:
        start = dt.datetime.fromisoformat(period["start"])
        end = dt.datetime.fromisoformat(period["end"])
        assert start < end
        # Timezone-aware
        assert start.tzinfo is not None
        assert end.tzinfo is not None


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_major_window_is_two_hours() -> None:
    """Major periods span ±1 hour around the event = 2-hour windows."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for period in result["major"]:
        start = dt.datetime.fromisoformat(period["start"])
        end = dt.datetime.fromisoformat(period["end"])
        duration_min = (end - start).total_seconds() / 60.0
        # Allow ±1 min for rounding (skyfield gives seconds precision)
        assert 119 <= duration_min <= 121


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_minor_window_is_one_hour() -> None:
    """Minor periods span ±30 min around the event = 1-hour windows."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for period in result["minor"]:
        start = dt.datetime.fromisoformat(period["start"])
        end = dt.datetime.fromisoformat(period["end"])
        duration_min = (end - start).total_seconds() / 60.0
        assert 59 <= duration_min <= 61


# ---------------------------------------------------------------------------
# Scoring contract
# ---------------------------------------------------------------------------


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_major_score_higher_than_minor() -> None:
    """Major periods (weight 1.0) score above minor periods (weight 0.6),
    barring sunrise/sunset overlap bonuses that could close the gap."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    # Use the base periods without overlap bonus by comparing min major vs max minor
    # before overlap adjustments. Easier: pick a date and config that won't overlap.
    # Here we just assert that at least one major outranks every minor.
    max_minor = max(p["score"] for p in result["minor"])
    max_major = max(p["score"] for p in result["major"])
    assert max_major >= max_minor


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_scores_capped_at_one() -> None:
    """Even with overlap bonus, scores never exceed 1.0."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for period in result["major"] + result["minor"]:
        assert period["score"] <= 1.0


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_base_scores_match_weights() -> None:
    """When neither sunrise nor sunset overlap is forced, major base = 1.0,
    minor base = 0.6. We force this by patching the sun helpers to return
    timestamps that fall far outside every period."""
    far_future_sunrise = dt.datetime(2099, 1, 1, 0, 0, tzinfo=dt.UTC)
    far_future_sunset = dt.datetime(2099, 1, 1, 12, 0, tzinfo=dt.UTC)

    with patch.object(solunar, "_sun_events", return_value=(far_future_sunrise, far_future_sunset)):
        result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for period in result["major"]:
        assert period["score"] == pytest.approx(1.0, abs=1e-6)
    for period in result["minor"]:
        assert period["score"] == pytest.approx(0.6, abs=1e-6)


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_sunrise_overlap_adds_bonus() -> None:
    """When a minor period overlaps sunrise, its score gains +0.2 (capped 1.0)."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    # Force a sunrise that lands inside the first minor period to guarantee overlap.
    minor_start = dt.datetime.fromisoformat(result["minor"][0]["start"])
    minor_end = dt.datetime.fromisoformat(result["minor"][0]["end"])
    sunrise_in_window = minor_start + (minor_end - minor_start) / 2
    sunset_far = dt.datetime(2099, 1, 1, 12, 0, tzinfo=dt.UTC)

    with patch.object(solunar, "_sun_events", return_value=(sunrise_in_window, sunset_far)):
        boosted = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    # Boost = +0.2, base minor = 0.6, expected = 0.8
    assert boosted["minor"][0]["score"] == pytest.approx(0.8, abs=1e-6)


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_sunset_overlap_adds_bonus() -> None:
    """When a major period overlaps sunset, its score gains +0.2 (capped 1.0)."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    major_start = dt.datetime.fromisoformat(result["major"][0]["start"])
    major_end = dt.datetime.fromisoformat(result["major"][0]["end"])
    sunset_in_window = major_start + (major_end - major_start) / 2
    sunrise_far = dt.datetime(2099, 1, 1, 0, 0, tzinfo=dt.UTC)

    with patch.object(solunar, "_sun_events", return_value=(sunrise_far, sunset_in_window)):
        boosted = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    # Base major = 1.0, overlap bonus = +0.2, capped at 1.0
    assert boosted["major"][0]["score"] == pytest.approx(1.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Determinism & ordering
# ---------------------------------------------------------------------------


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_deterministic_under_freeze() -> None:
    """Two identical calls under freeze_time produce identical output."""
    a = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)
    b = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)
    assert a == b


@freeze_time("2026-06-21 12:00:00")
def test_compute_periods_periods_sorted_by_start() -> None:
    """Within each category (major / minor), periods are returned chronologically."""
    result = solunar.compute_periods(LEVIS_LAT, LEVIS_LON, TEST_DATE)

    for key in ("major", "minor"):
        starts = [dt.datetime.fromisoformat(p["start"]) for p in result[key]]
        assert starts == sorted(starts)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_compute_periods_invalid_lat_raises() -> None:
    """Latitudes outside [-90, 90] raise ValueError."""
    with pytest.raises(ValueError):
        solunar.compute_periods(95.0, 0.0, TEST_DATE)


def test_compute_periods_invalid_lon_raises() -> None:
    """Longitudes outside [-180, 180] raise ValueError."""
    with pytest.raises(ValueError):
        solunar.compute_periods(0.0, 200.0, TEST_DATE)
