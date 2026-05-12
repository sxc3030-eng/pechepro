"""ECCC (Environment and Climate Change Canada) water temperature client.

Spec: docs/superpowers/specs/2026-05-09-pechepro-design.md §3.3, §7
Canonical signature: docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md

API: https://api.weather.gc.ca/collections/hydrometric-realtime/items?...

Coverage is sparse — ECCC hydrometric stations measure flow (discharge) primarily,
temperature is secondary metadata. Most Canadian lakes have no station. We fail
gracefully (return None) when no data is available so the recommender can fall
back to user-provided / default values.

The public API is sync (Flask 3 routes are sync); httpx is used in sync mode.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ECCC_URL = "https://api.weather.gc.ca/collections/hydrometric-realtime/items"
_TIMEOUT_SECONDS = 5.0
_BBOX_RADIUS_DEG = 0.5

# Canada coarse bbox + US-shaded sub-bboxes to subtract.
# Per V0.1 spec, false-negatives near the border (point classified as US when in
# Canada) are acceptable — the recommender tolerates a None water temperature.
# False-positives (US point routed to ECCC) are worse because we'd pay an HTTP
# call for nothing and possibly return a US station as if it were Canadian.
#
# Source: NRCan — Canada extent (lat 41.7 to 83.1, lon -141.0 to -52.6).
_CA_LAT_MIN, _CA_LAT_MAX = 41.7, 83.1
_CA_LON_MIN, _CA_LON_MAX = -141.0, -52.6

# US states wedged into the Canadian outer bbox that we explicitly subtract.
# Each entry is (lat_min, lat_max, lon_min, lon_max). Points inside any of
# these boxes are treated as US (return None, no API call).
#
# We err on the side of *under-subtracting* on the Great Lakes border (where
# US shore and Canadian shore share latitude/longitude bands): a US point in
# that zone will hit the ECCC API and get an empty FeatureCollection back —
# correct return value of None, just with one wasted HTTP call. Better that
# than excluding Toronto / Windsor / Halifax / Vancouver from coverage.
_US_SUB_BBOXES: tuple[tuple[float, float, float, float], ...] = (
    # New England (VT, NH, ME, MA, RI, CT) — east of Lake Champlain (~-73.4°W),
    # south of Quebec's southern border at ~45°N.
    (41.7, 45.0, -73.4, -66.9),
    # Pacific Northwest below 49°N (WA, OR strip).
    # Canada's BC south border is at 49°N exactly.
    (41.7, 48.99, -124.8, -117.0),
    # NB: We deliberately do NOT subtract the upstate-NY / Great Lakes / Detroit
    # band (lat 41.7-44, lon -79.4 to -73.4 and Great Lakes area). Toronto,
    # Hamilton, Niagara Falls ON, Windsor, all sit there. A simple bbox cannot
    # separate them from Buffalo / Detroit / Cleveland. False-positives (US point
    # routed to ECCC) get an empty FeatureCollection back — observable result is
    # still None, just costs one wasted HTTP call. Better than excluding Toronto.
)


def _is_valid_coords(lat: float, lon: float) -> bool:
    """Basic earth-coord sanity check."""
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _in_us_sub_bbox(lat: float, lon: float) -> bool:
    for lat_min, lat_max, lon_min, lon_max in _US_SUB_BBOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return True
    return False


def _is_in_canada(lat: float, lon: float) -> bool:
    """Cheap bbox check — short-circuits before any HTTP call for non-CA queries.

    Excludes US states wedged into the Canadian outer bbox (New England,
    upstate NY, Great Lakes states, western Midwest below 49°N).
    """
    in_outer = _CA_LAT_MIN <= lat <= _CA_LAT_MAX and _CA_LON_MIN <= lon <= _CA_LON_MAX
    if not in_outer:
        return False
    return not _in_us_sub_bbox(lat, lon)


def _extract_first_temperature(data: dict[str, Any]) -> float | None:
    """Pick the first feature with a sane WATER_TEMPERATURE value.

    ECCC GeoJSON shape:
        {"type": "FeatureCollection",
         "features": [{"properties": {"WATER_TEMPERATURE": float | null, ...}, ...}, ...]}
    """
    features = data.get("features", [])
    if not isinstance(features, list):
        return None
    for feature in features:
        props = feature.get("properties", {}) if isinstance(feature, dict) else {}
        raw = props.get("WATER_TEMPERATURE")
        if raw is None:
            continue
        try:
            parsed = float(raw)
        except (TypeError, ValueError):
            continue
        if -50.0 < parsed < 50.0:  # sanity bounds (frozen lake / boiling)
            return parsed
    return None


def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temperature in Celsius from the nearest ECCC station, or None.

    Coverage is limited — ECCC hydrometric stations primarily measure flow;
    temperature is secondary metadata, so most Canadian lakes have no station.
    Returning None is a normal outcome; the Open-Meteo / USGS clients carry
    the load and the recommender tolerates a None water temperature.

    Returns None when:
    - (lat, lon) is invalid or outside Canada bounds (short-circuits, no HTTP call)
    - The API has no nearby station with temperature data
    - The API times out, errors, or returns malformed JSON

    Never raises — graceful failure is the contract.
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
    params: dict[str, str | int] = {
        "f": "json",
        "bbox": bbox,
        "limit": 50,
        "properties": "STATION_NUMBER,STATION_NAME,WATER_TEMPERATURE,DATE",
    }

    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.get(_ECCC_URL, params=params)
        if response.status_code != 200:
            logger.warning("ECCC API returned %s for bbox=%s", response.status_code, bbox)
            return None
        data = response.json()
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        logger.warning("ECCC network error: %s", exc)
        return None
    except ValueError as exc:  # JSON decode error
        logger.warning("ECCC malformed JSON: %s", exc)
        return None

    if not isinstance(data, dict):
        return None
    return _extract_first_temperature(data)
