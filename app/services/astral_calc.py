"""Local sun & moon calculations via astral 3.x + skyfield 1.49. No network at call time.

The skyfield ephemeris file ``de421.bsp`` (~17 MB) is downloaded once on the first
call and cached under ``%LOCALAPPDATA%/pechepro/skyfield`` (Windows) or
``~/.cache/pechepro/skyfield`` (other OSes). Subsequent calls are fully offline.

Canonical signature (from ``docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md``)::

    def sun_moon(lat: float, lon: float, date: datetime.date) -> dict[str, Any]
"""

from __future__ import annotations

import datetime as dt
import math
import os
from pathlib import Path
from typing import Any, cast

from astral import LocationInfo, moon
from astral.sun import sun

# Lazy-loaded skyfield handles. Loaded on first ``sun_moon`` call. After load they
# stay resident for the lifetime of the Python process.
_EPHEMERIS: Any = None
_TS: Any = None


def _ephemeris_cache_dir() -> Path:
    """Return the directory where the de421.bsp ephemeris file is cached.

    On Windows uses ``%LOCALAPPDATA%/pechepro/skyfield``; otherwise falls back to
    ``~/.cache/pechepro/skyfield``. The directory is created if missing.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        cache = Path(base) / "pechepro" / "skyfield"
    else:
        cache = Path.home() / ".cache" / "pechepro" / "skyfield"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _load_ephemeris() -> tuple[Any, Any]:
    """Load skyfield ephemeris (de421.bsp ~17 MB) and timescale once."""
    global _EPHEMERIS, _TS
    if _EPHEMERIS is None:
        from skyfield.iokit import Loader

        load = Loader(str(_ephemeris_cache_dir()), verbose=False)
        _TS = load.timescale()
        _EPHEMERIS = load("de421.bsp")
    return _EPHEMERIS, _TS


def _classify_moon_phase(phase_value: float) -> str:
    """Convert ``astral.moon.phase()`` value (0..28) into a 4-bucket label.

    Boundaries::

        [ 0.0,  7.0)  -> "new"
        [ 7.0, 14.0)  -> "waxing"
        [14.0, 21.0)  -> "full"
        [21.0, 28.0]  -> "waning"
    """
    if phase_value < 7.0:
        return "new"
    if phase_value < 14.0:
        return "waxing"
    if phase_value < 21.0:
        return "full"
    return "waning"


def _moon_illumination(phase_value: float) -> float:
    """Approximate moon illumination fraction (0..1) from astral phase value (0..28).

    Uses ``(1 - cos(angle)) / 2`` where ``angle`` maps phase 0 -> 0 rad (new, dark)
    and phase 14 -> pi rad (full, fully lit). Returns 0 at the new-moon endpoints,
    1 at the full-moon midpoint, and is symmetric around the full moon.
    """
    angle = (phase_value / 28.0) * 2.0 * math.pi
    illum = (1.0 - math.cos(angle)) / 2.0
    # Defensive clamp; floating-point can drift a hair outside [0, 1].
    return float(max(0.0, min(1.0, illum)))


def _moon_transits(lat: float, lon: float, date: dt.date) -> tuple[str, str]:
    """Return ``(transit_iso, underfoot_iso)`` for the given lat/lon/date.

    *Transit* (upper meridian) = the moon is at its highest point.
    *Underfoot* (lower / anti-meridian) = the moon is at its lowest point below the horizon.

    Both are ISO 8601 strings (UTC). Empty string if no event occurs in the 24 h UTC
    window of ``date`` — which is normal: the moon transits roughly every ~24h50m, so
    on some days only one of the two events falls within the calendar day.
    """
    from skyfield import almanac
    from skyfield.api import wgs84

    eph, ts = _load_ephemeris()
    t0 = ts.utc(date.year, date.month, date.day, 0, 0, 0)
    next_day = date + dt.timedelta(days=1)
    t1 = ts.utc(next_day.year, next_day.month, next_day.day, 0, 0, 0)

    transit_fn = almanac.meridian_transits(eph, eph["moon"], wgs84.latlon(lat, lon))
    times, events = almanac.find_discrete(t0, t1, transit_fn)

    transit_iso = ""
    underfoot_iso = ""
    for t, e in zip(times, events, strict=False):
        iso = t.utc_iso()
        # almanac.MERIDIAN_TRANSITS: 0 = "Antimeridian transit" (underfoot),
        # 1 = "Meridian transit" (upper transit).
        if int(e) == 1 and not transit_iso:
            transit_iso = iso
        elif int(e) == 0 and not underfoot_iso:
            underfoot_iso = iso
    return transit_iso, underfoot_iso


def sun_moon(lat: float, lon: float, date: dt.date) -> dict[str, Any]:
    """Compute sun/moon parameters for ``lat``/``lon`` on ``date``.

    Returns a dict with these keys:

    - ``sunrise``, ``sunset``: ISO 8601 timestamp strings (empty string if the sun
      does not rise/set on this day at this latitude, e.g. polar night).
    - ``civil_dawn``, ``civil_dusk``: 6° depression dawn/dusk; ISO or empty string.
    - ``nautical_dawn``, ``nautical_dusk``: 12° depression dawn/dusk; ISO or empty string.
    - ``moon_phase``: one of ``"new"``, ``"waxing"``, ``"full"``, ``"waning"``.
    - ``moon_illumination``: float in [0, 1].
    - ``moon_transit``, ``moon_underfoot``: ISO 8601 timestamps (UTC); empty string
      if the event does not occur in the 24 h UTC window of ``date``.

    Raises:
        ValueError: if ``lat`` outside [-90, 90] or ``lon`` outside [-180, 180].
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"lat must be in [-90, 90], got {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"lon must be in [-180, 180], got {lon}")

    loc = LocationInfo(name="local", region="", timezone="UTC", latitude=lat, longitude=lon)

    def _safe_sun(depression: float | None = None) -> dict[str, Any]:
        try:
            if depression is None:
                return cast(dict[str, Any], sun(loc.observer, date=date))
            return cast(
                dict[str, Any], sun(loc.observer, date=date, dawn_dusk_depression=depression)
            )
        except ValueError:
            # astral raises ValueError for polar day / polar night
            return {"sunrise": None, "sunset": None, "dawn": None, "dusk": None}

    s = _safe_sun()
    civil = _safe_sun(6.0)
    nautical = _safe_sun(12.0)

    def _iso(value: dt.datetime | None) -> str:
        if value is None:
            return ""
        return value.isoformat()

    phase_val = moon.phase(date)
    try:
        transit_iso, underfoot_iso = _moon_transits(lat, lon, date)
    except Exception:  # pragma: no cover
        # Network / ephemeris load failure is integration-level; fall back to empty.
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
