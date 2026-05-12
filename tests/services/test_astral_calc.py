"""Tests for app.services.astral_calc.

Local sun/moon calculations via astral 3.x + skyfield 1.49 — no network at call time.
"""

from __future__ import annotations

import datetime as dt

import pytest
from freezegun import freeze_time

from app.services import astral_calc

# --- Task 2 : happy path ----------------------------------------------------


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
    assert "T" in result["civil_dawn"]
    assert "T" in result["nautical_dawn"]
    # Lévis on the summer solstice has both a moon transit and an underfoot in the UTC day
    assert "T" in result["moon_transit"]
    assert "T" in result["moon_underfoot"]
    # Moon phase is one of the 4 buckets
    assert result["moon_phase"] in {"new", "waxing", "full", "waning"}
    # Illumination is a fraction 0..1
    assert 0.0 <= result["moon_illumination"] <= 1.0


# --- Task 3 : extreme latitude + lat/lon validation -------------------------


@freeze_time("2026-12-21 12:00:00")
def test_sun_moon_arctic_winter_handled_gracefully() -> None:
    """Above the Arctic Circle in December the sun never rises.

    astral raises ValueError for polar night; the wrapper must catch it and return
    empty strings for sun events while keeping moon data computable.
    """
    result = astral_calc.sun_moon(lat=70.0, lon=-150.0, date=dt.date(2026, 12, 21))
    # Sun never rises: event strings either ISO or empty (graceful fallback)
    assert isinstance(result["sunrise"], str)
    assert isinstance(result["sunset"], str)
    # At 70°N, 21 Dec the sun is always below the horizon -> both should be empty
    assert result["sunrise"] == ""
    assert result["sunset"] == ""
    # Moon data is still computable
    assert result["moon_phase"] in {"new", "waxing", "full", "waning"}
    assert 0.0 <= result["moon_illumination"] <= 1.0


@freeze_time("2026-06-21 12:00:00")
def test_sun_moon_antarctic_summer_handled_gracefully() -> None:
    """South Pole at the southern winter solstice (= sun never rises): graceful empty."""
    result = astral_calc.sun_moon(lat=-80.0, lon=0.0, date=dt.date(2026, 6, 21))
    # Both polar-night events fall back to empty strings, not exceptions.
    assert result["sunrise"] == ""
    assert result["sunset"] == ""
    # Civil/nautical also empty under polar night
    assert result["civil_dawn"] == ""
    assert result["nautical_dawn"] == ""
    # Moon data still computable
    assert result["moon_phase"] in {"new", "waxing", "full", "waning"}


@freeze_time("2026-03-20 12:00:00")
def test_sun_moon_equator_returns_valid_iso() -> None:
    """At the equator on equinox, day and night are ~equal — sun rises and sets cleanly."""
    result = astral_calc.sun_moon(lat=0.0, lon=0.0, date=dt.date(2026, 3, 20))
    assert "T" in result["sunrise"]
    assert "T" in result["sunset"]
    assert "T" in result["civil_dawn"]
    assert "T" in result["civil_dusk"]


@freeze_time("2030-09-15 12:00:00")
def test_sun_moon_future_date_2030_deterministic() -> None:
    """A date in 2030 must compute deterministically (ephemeris covers ~1900-2050)."""
    result = astral_calc.sun_moon(lat=46.81, lon=-71.21, date=dt.date(2030, 9, 15))
    # All keys are still produced
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
    assert "T" in result["sunrise"]
    assert "T" in result["sunset"]
    # Lévis on 2030-09-15 should have a moon transit AND an underfoot in the UTC day
    assert "T" in result["moon_transit"]
    assert "T" in result["moon_underfoot"]
    # Two calls under the same freeze are byte-identical (no flaky tests)
    again = astral_calc.sun_moon(lat=46.81, lon=-71.21, date=dt.date(2030, 9, 15))
    assert result == again


def test_sun_moon_invalid_lat_too_high_raises() -> None:
    """Out-of-bounds latitude (>90) raises ValueError before hitting astral."""
    with pytest.raises(ValueError, match="lat"):
        astral_calc.sun_moon(lat=95.0, lon=0.0, date=dt.date(2026, 6, 21))


def test_sun_moon_invalid_lat_too_low_raises() -> None:
    """Out-of-bounds latitude (<-90) raises ValueError."""
    with pytest.raises(ValueError, match="lat"):
        astral_calc.sun_moon(lat=-95.0, lon=0.0, date=dt.date(2026, 6, 21))


def test_sun_moon_invalid_lon_too_high_raises() -> None:
    """Out-of-bounds longitude (>180) raises ValueError."""
    with pytest.raises(ValueError, match="lon"):
        astral_calc.sun_moon(lat=0.0, lon=200.0, date=dt.date(2026, 6, 21))


def test_sun_moon_invalid_lon_too_low_raises() -> None:
    """Out-of-bounds longitude (<-180) raises ValueError."""
    with pytest.raises(ValueError, match="lon"):
        astral_calc.sun_moon(lat=0.0, lon=-200.0, date=dt.date(2026, 6, 21))


def test_sun_moon_boundary_lat_lon_accepted() -> None:
    """Exact bounds ±90 / ±180 are accepted (inclusive)."""
    # Just confirm no ValueError is raised at the bounds.
    result = astral_calc.sun_moon(lat=90.0, lon=180.0, date=dt.date(2026, 6, 21))
    assert isinstance(result, dict)
    result = astral_calc.sun_moon(lat=-90.0, lon=-180.0, date=dt.date(2026, 6, 21))
    assert isinstance(result, dict)
