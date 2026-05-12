"""USGS Water Services client — water temperature for US lat/lon.

API: https://waterservices.usgs.gov/nwis/iv/?format=json&parameterCd=00010&...
parameterCd 00010 = "Temperature, water, degrees Celsius".
No API key required.

Canonical signature (cross-plan amendments 2026-05-09):
    def get_water_temp(lat: float, lon: float) -> float | None
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_USGS_URL = "https://waterservices.usgs.gov/nwis/iv/"
_TIMEOUT_SECONDS = 5.0

# ~0.5° around the requested lat/lon (~55km at the equator, less near the poles).
_BBOX_RADIUS_DEG = 0.5

# Maximum acceptable distance from the requested lat/lon to the closest station.
_MAX_STATION_DISTANCE_KM = 50.0

# Maximum age of a temperature reading before it is considered stale.
_MAX_READING_AGE_DAYS = 7

# Conterminous US bounding box (Alaska + Hawaii intentionally excluded for V0.1).
# A simple rectangle (lat 24.5-49.4, lon -125.0 to -66.9) would include large
# parts of southern Canada (Vancouver, Toronto, Montreal, Lévis…) because the
# US-Canada border isn't a single line of latitude. We use a piecewise
# longitude → max-latitude map that follows the real border closely enough
# for "is this a US fishing spot" purposes.
_US_LAT_MIN = 24.5
_US_LON_MIN, _US_LON_MAX = -125.0, -66.9

# (lon_max_inclusive, lat_max) — first row that matches a given longitude wins.
# Longitudes increase from west (-125) to east (-66.9).
# Reference points:
#   - West of -95° (Pacific NW / Plains / Rockies): US-Canada border ~49°N
#     (Northwest Angle MN is the only exception at 49.38°N — accepted as
#      false-negative cost since no major population there).
#   - -95° to -82° (Great Lakes northern): border runs through Lake Superior
#     and the Boundary Waters ~48°N at most.
#   - -82° to -68° (NY/PA/OH/VT/NH/Western ME): border drops to ~45°N
#     (St-Lawrence valley, Vermont/Quebec 45th parallel, southern Ontario).
#   - East of -68° (Eastern Maine / Madawaska): border kinks up to ~47.5°N.
_US_LAT_CAP_BY_LON: tuple[tuple[float, float], ...] = (
    (-95.0, 49.0),
    (-82.0, 48.5),
    (-68.0, 45.5),
    (-66.9, 47.5),
)

# USGS uses this sentinel value to indicate a missing reading.
_USGS_MISSING_SENTINEL = -999999.0

_EARTH_RADIUS_KM = 6371.0


def _is_valid_coords(lat: float, lon: float) -> bool:
    """Reject out-of-range lat/lon without hitting the network."""
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _is_in_us(lat: float, lon: float) -> bool:
    """True if (lat, lon) is inside the conterminous US (piecewise bbox).

    The eastern US has a much lower upper latitude than the western US because
    the US-Canada border drops to the 45th parallel between Maine and
    Minnesota. A plain rectangle would falsely admit southern Quebec / Ontario
    / BC, so we use a longitude → max-latitude lookup.
    """
    if lat < _US_LAT_MIN:
        return False
    if not _US_LON_MIN <= lon <= _US_LON_MAX:
        return False
    for lon_max, lat_cap in _US_LAT_CAP_BY_LON:
        if lon <= lon_max:
            return lat <= lat_cap
    # lon > _US_LON_MAX is already rejected above.
    return False


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two WGS84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_KM * c


def _parse_usgs_datetime(value: str) -> dt.datetime | None:
    """Parse a USGS ISO-8601 dateTime ('2026-06-21T12:00:00.000-05:00').

    Returns a timezone-aware datetime, or None if the value can't be parsed.
    """
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        # USGS responses are typically tz-aware, but normalise just in case.
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed


def _parse_sample(
    sample: dict[str, Any],
    *,
    now: dt.datetime,
) -> tuple[dt.datetime, float] | None:
    """Parse one USGS sample dict; return (time, temp_c) if it's a fresh reading."""
    raw_value = sample.get("value")
    try:
        temp = float(raw_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if temp <= _USGS_MISSING_SENTINEL + 1.0:
        # USGS missing-value marker (or anything obviously bogus).
        return None

    sample_time = _parse_usgs_datetime(sample.get("dateTime", ""))
    if sample_time is None:
        return None
    age = now - sample_time
    if age.total_seconds() < 0:
        # Future-dated reading — treat as fresh.
        age = dt.timedelta(0)
    if age > dt.timedelta(days=_MAX_READING_AGE_DAYS):
        return None
    return sample_time, temp


def _extract_station_temperature(
    series: dict[str, Any],
    *,
    now: dt.datetime,
) -> tuple[float, float, float] | None:
    """Pull (lat, lon, temp_c) from a single USGS timeSeries entry.

    Returns None if the series has no fresh, non-sentinel reading.
    """
    geo = series.get("sourceInfo", {}).get("geoLocation", {}).get("geogLocation", {})
    try:
        site_lat = float(geo["latitude"])
        site_lon = float(geo["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

    # Walk every value block and pick the freshest non-sentinel reading.
    best_value: float | None = None
    best_time: dt.datetime | None = None
    for value_block in series.get("values", []):
        for sample in value_block.get("value", []):
            parsed = _parse_sample(sample, now=now)
            if parsed is None:
                continue
            sample_time, temp = parsed
            if best_time is None or sample_time > best_time:
                best_time = sample_time
                best_value = temp

    if best_value is None:
        return None
    return site_lat, site_lon, best_value


def _pick_closest_temperature(
    data: dict[str, Any],
    *,
    target_lat: float,
    target_lon: float,
    now: dt.datetime,
) -> float | None:
    """Find the closest USGS station with a fresh reading; return its temp in °C."""
    series = data.get("value", {}).get("timeSeries", [])
    if not isinstance(series, list):
        return None

    best_distance = math.inf
    best_temp: float | None = None
    for ts in series:
        extracted = _extract_station_temperature(ts, now=now)
        if extracted is None:
            continue
        site_lat, site_lon, temp = extracted
        distance = _haversine_km(target_lat, target_lon, site_lat, site_lon)
        if distance > _MAX_STATION_DISTANCE_KM:
            continue
        if distance < best_distance:
            best_distance = distance
            best_temp = temp
    return best_temp


def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temperature in Celsius from the nearest USGS station, or None.

    Returns None if:
      - lat/lon is outside conterminous US bbox (no network call)
      - lat/lon is otherwise out of range (no network call)
      - USGS API times out / returns non-200 / raises a network error
      - USGS returns malformed JSON
      - No USGS station with a fresh reading within ~50 km radius
      - Station's most recent temperature reading is older than 7 days
      - Station's reading is the USGS missing-value sentinel (-999999)

    Uses the USGS Water Services Instantaneous Values API (no key required):
        https://waterservices.usgs.gov/nwis/iv/?format=json&parameterCd=00010&bBox=...

    parameterCd 00010 = "Temperature, water, degrees Celsius".
    """
    if not _is_valid_coords(lat, lon):
        return None
    if not _is_in_us(lat, lon):
        return None

    # USGS expects bBox as "minLon,minLat,maxLon,maxLat" (west, south, east, north).
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
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.get(_USGS_URL, params=params)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
        logger.warning("USGS network error: %s", exc)
        return None

    if response.status_code != 200:
        logger.warning(
            "USGS API returned status=%s for bbox=%s",
            response.status_code,
            bbox,
        )
        return None

    try:
        data = response.json()
    except ValueError as exc:
        logger.warning("USGS malformed JSON: %s", exc)
        return None

    now = dt.datetime.now(tz=dt.UTC)
    return _pick_closest_temperature(data, target_lat=lat, target_lon=lon, now=now)
