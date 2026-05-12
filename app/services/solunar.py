"""Solunar major/minor period computation for pechepro.

Major periods (weight 1.0) = moon transit (overhead) ±1h and moon underfoot ±1h.
Minor periods (weight 0.6) = moonrise ±30min and moonset ±30min.

Score bonus: +0.2 if a period overlaps sunrise or sunset (capped at 1.0).

Implementation note: this module owns its own skyfield ephemeris loader so it
remains independent of `app.services.astral_calc` (which is built by a parallel
worktree). The de421 ephemeris file is downloaded once into
``%LOCALAPPDATA%\\pechepro\\skyfield`` and reused for every subsequent call.
"""

from __future__ import annotations

import datetime as dt
import os
import threading
from pathlib import Path
from typing import Any

from skyfield import almanac  # type: ignore[import-untyped, unused-ignore]
from skyfield.api import Loader, wgs84  # type: ignore[import-untyped, unused-ignore]

# Skyfield ships no py.typed marker, so its symbols come through as untyped.
# We annotate skyfield-derived values as Any (see the project mypy config:
# `disallow_any_unimported = true`).

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAJOR_HALF_WINDOW = dt.timedelta(hours=1)  # ±1h → 2-hour window
_MINOR_HALF_WINDOW = dt.timedelta(minutes=30)  # ±30min → 1-hour window

_MAJOR_WEIGHT = 1.0
_MINOR_WEIGHT = 0.6
_OVERLAP_BONUS = 0.2
_SCORE_CAP = 1.0

# skyfield almanac event codes:
#   meridian_transits: True = west of meridian; transition False→True (event=1)
#       = upper meridian crossing (transit/overhead); True→False (event=0)
#       = anti-meridian crossing (underfoot).
#   risings_and_settings: True = above horizon; event=1 = rise, event=0 = set.
_EVENT_TRANSIT_UPPER = 1
_EVENT_TRANSIT_LOWER = 0
_EVENT_RISE = 1
_EVENT_SET = 0


# ---------------------------------------------------------------------------
# Skyfield loader (lazy singleton)
# ---------------------------------------------------------------------------


def _cache_dir() -> Path:
    """Return the directory where skyfield ephemeris files are cached.

    Honors PECHEPRO_SKYFIELD_CACHE for tests and CI; falls back to
    %LOCALAPPDATA%\\pechepro\\skyfield on Windows, or ~/.cache/pechepro/skyfield
    elsewhere.
    """
    override = os.environ.get("PECHEPRO_SKYFIELD_CACHE")
    if override:
        return Path(override)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "pechepro" / "skyfield"
    return Path.home() / ".cache" / "pechepro" / "skyfield"


_loader_lock = threading.Lock()
_loader: Any = None
_eph: Any = None
_ts: Any = None


def _get_loader() -> tuple[Any, Any]:
    """Return (ephemeris, timescale), creating them on first call (thread-safe)."""
    global _loader, _eph, _ts
    if _eph is not None and _ts is not None:
        return _eph, _ts
    with _loader_lock:
        if _eph is None or _ts is None:
            cache = _cache_dir()
            cache.mkdir(parents=True, exist_ok=True)
            _loader = Loader(str(cache))
            _eph = _loader("de421.bsp")
            _ts = _loader.timescale()
    return _eph, _ts


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate(lat: float, lon: float) -> None:
    """Reject coordinates outside the geographic range."""
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"lat must be in [-90, 90], got {lat}")
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"lon must be in [-180, 180], got {lon}")


def _day_bounds(date: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """Return UTC midnight..midnight bounds covering the requested local date.

    For a simple desktop-app contract we treat ``date`` as a UTC day.  This is
    accurate enough for North-American latitudes given that the user's
    longitude is supplied separately and that we surface ISO timestamps with
    explicit UTC offsets — the UI layer applies any local-tz formatting.
    """
    start = dt.datetime.combine(date, dt.time(0, 0), tzinfo=dt.UTC)
    end = start + dt.timedelta(days=1)
    return start, end


def _topos(lat: float, lon: float) -> Any:
    """Return a skyfield ``GeographicPosition`` for the given coordinates."""
    return wgs84.latlon(lat, lon)


def _find_events(
    finder: Any,
    start: dt.datetime,
    end: dt.datetime,
) -> list[tuple[dt.datetime, int]]:
    """Run almanac.find_discrete and return (utc_datetime, event_code) tuples."""
    _, ts = _get_loader()
    t0 = ts.from_datetime(start)
    t1 = ts.from_datetime(end)
    times, events = almanac.find_discrete(t0, t1, finder)
    out: list[tuple[dt.datetime, int]] = []
    for ti, ev in zip(times, events, strict=False):
        utc_dt = ti.utc_datetime().replace(tzinfo=dt.UTC)
        out.append((utc_dt, int(ev)))
    return out


def _moon_transits(
    topos: Any, start: dt.datetime, end: dt.datetime
) -> tuple[list[dt.datetime], list[dt.datetime]]:
    """Return (upper_transits, lower_transits) — moon overhead and underfoot."""
    eph, _ = _get_loader()
    finder = almanac.meridian_transits(eph, eph["Moon"], topos)
    events = _find_events(finder, start, end)
    upper = [t for t, ev in events if ev == _EVENT_TRANSIT_UPPER]
    lower = [t for t, ev in events if ev == _EVENT_TRANSIT_LOWER]
    return upper, lower


def _moon_rise_set(
    topos: Any, start: dt.datetime, end: dt.datetime
) -> tuple[list[dt.datetime], list[dt.datetime]]:
    """Return (rises, settings) for the moon over the day window."""
    eph, _ = _get_loader()
    finder = almanac.risings_and_settings(eph, eph["Moon"], topos)
    events = _find_events(finder, start, end)
    rises = [t for t, ev in events if ev == _EVENT_RISE]
    sets = [t for t, ev in events if ev == _EVENT_SET]
    return rises, sets


def _sun_events(
    lat: float, lon: float, date: dt.date
) -> tuple[dt.datetime | None, dt.datetime | None]:
    """Return (sunrise_utc, sunset_utc) for the day, or None when absent (polar)."""
    topos = _topos(lat, lon)
    eph, _ = _get_loader()
    start, end = _day_bounds(date)
    finder = almanac.risings_and_settings(eph, eph["Sun"], topos)
    events = _find_events(finder, start, end)
    rises = [t for t, ev in events if ev == _EVENT_RISE]
    sets = [t for t, ev in events if ev == _EVENT_SET]
    sunrise = rises[0] if rises else None
    sunset = sets[0] if sets else None
    return sunrise, sunset


def _windows_overlap(
    a_start: dt.datetime,
    a_end: dt.datetime,
    b: dt.datetime | None,
) -> bool:
    """True when timestamp ``b`` falls inside ``[a_start, a_end]``."""
    if b is None:
        return False
    return a_start <= b <= a_end


def _build_period(
    center: dt.datetime,
    half: dt.timedelta,
    base_weight: float,
    sunrise: dt.datetime | None,
    sunset: dt.datetime | None,
) -> dict[str, Any]:
    """Build a single period dict with start/end ISO strings and a final score."""
    start = center - half
    end = center + half
    score = base_weight
    if _windows_overlap(start, end, sunrise) or _windows_overlap(start, end, sunset):
        score += _OVERLAP_BONUS
    score = min(score, _SCORE_CAP)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "score": float(score),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_periods(lat: float, lon: float, date: dt.date) -> dict[str, Any]:
    """Compute solunar major and minor periods for a location and date.

    Major periods (weight 1.0): moon transit (overhead) and moon underfoot,
        ±1 hour each (2-hour windows).
    Minor periods (weight 0.6): moonrise and moonset,
        ±30 min each (1-hour windows).
    Score adjustments: +0.2 when a period overlaps sunrise or sunset,
        capped at 1.0.

    Args:
        lat: Latitude in degrees, range [-90, 90].
        lon: Longitude in degrees, range [-180, 180].
        date: Calendar day (UTC) for which to compute periods.

    Returns:
        {
            'major': [{'start': iso, 'end': iso, 'score': float}, ...],
            'minor': [{'start': iso, 'end': iso, 'score': float}, ...],
        }
        Both lists are sorted by start time. Empty lists are returned for
        polar / no-event days.

    Raises:
        ValueError: If lat or lon is outside its valid range.
    """
    _validate(lat, lon)

    topos = _topos(lat, lon)
    start, end = _day_bounds(date)

    upper, lower = _moon_transits(topos, start, end)
    rises, sets = _moon_rise_set(topos, start, end)
    sunrise, sunset = _sun_events(lat, lon, date)

    major: list[dict[str, Any]] = []
    for center in upper + lower:
        major.append(_build_period(center, _MAJOR_HALF_WINDOW, _MAJOR_WEIGHT, sunrise, sunset))

    minor: list[dict[str, Any]] = []
    for center in rises + sets:
        minor.append(_build_period(center, _MINOR_HALF_WINDOW, _MINOR_WEIGHT, sunrise, sunset))

    major.sort(key=lambda p: p["start"])
    minor.sort(key=lambda p: p["start"])

    return {"major": major, "minor": minor}
