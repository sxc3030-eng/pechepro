"""Tests for app.services.astral_calc.

Local sun/moon calculations via astral 3.x + skyfield 1.49 — no network at call time.
"""

from __future__ import annotations

import datetime as dt

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
