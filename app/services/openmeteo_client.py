"""Open-Meteo sync client with SQLite cache (TTL 1h).

Canonical signature (cross-plan amendments, 2026-05-09):

    def get_weather(lat: float, lon: float, db: sqlite3.Connection | None = None)
        -> dict[str, Any]

Public API is **sync** (Flask 3 routes are sync). Internally we use
``httpx.Client`` directly — no asyncio wrapping required.

Endpoint:
    https://api.open-meteo.com/v1/forecast — no API key required.

Rate limit mitigation:
    Cache_key = "round(lat,2),round(lon,2)" → users within ~1km share the
    cache row. TTL = 3600 s. Spec §11.

Failure handling:
    Timeouts and 5xx responses trigger up to 2 retries (3 attempts total)
    with exponential backoff (0.2 s, 0.4 s). Permanent failures (4xx,
    malformed body, exhausted retries) raise ``ServiceUnavailable`` which
    the Flask error handler maps to HTTP 503 (spec §7).
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from typing import Any

import httpx

from app.services.errors import ServiceUnavailable

__all__ = ["get_weather"]

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_CACHE_TTL_SECONDS = 3600
_TIMEOUT_SECONDS = 5.0
_MAX_RETRIES = 2  # → 3 attempts total
_RETRY_BACKOFF_SECONDS = 0.2
_SOURCE = "open-meteo"
_VALID_TRENDS = ("rising", "falling", "steady")
_TREND_STEADY_DELTA_HPA = 1.0  # < 1 hPa over the window is "steady"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_weather(
    lat: float,
    lon: float,
    db: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Sync wrapper around the Open-Meteo Forecast API.

    Args:
        lat: WGS84 latitude.
        lon: WGS84 longitude.
        db: optional SQLite connection. When provided, results are cached in
            the ``weather_cache`` table (TTL 1 h, key rounded to 2 decimals).

    Returns:
        A dict with the canonical fields:

            temp_air_c:               float, current air temperature (°C)
            pressure_hpa:             float, current MSL pressure (hPa)
            pressure_trend_6h:        'rising' | 'falling' | 'steady'
            pressures_history_hpa:    list[float] of the last 6 hourly MSL pressures
            humidity_pct:             float, current relative humidity (%)
            wind_kmh:                 float, current 10 m wind speed (km/h)
            cloud_cover_pct:          float, current total cloud cover (%)
            fetched_at:               ISO-8601 UTC timestamp of the fetch
            cached:                   bool, True if served from cache, else False
            source:                   'open-meteo'

    Raises:
        ServiceUnavailable: on timeout, 5xx after 2 retries, 4xx, or malformed
            response body.
    """
    if db is not None:
        cached = _read_cache(db, lat, lon)
        if cached is not None:
            cached["cached"] = True
            return cached

    fresh = _fetch_remote_with_retries(lat, lon)
    fresh["cached"] = False

    if db is not None:
        _write_cache(db, lat, lon, fresh)

    return fresh


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(lat: float, lon: float) -> str:
    """Round to 2 decimals (~1 km) so nearby users share the cache row."""
    return f"{round(lat, 2)},{round(lon, 2)}"


def _read_cache(db: sqlite3.Connection, lat: float, lon: float) -> dict[str, Any] | None:
    """Return the cached payload if its ``expires_at`` is in the future."""
    key = _cache_key(lat, lon)
    row = db.execute(
        "SELECT payload_json, expires_at FROM weather_cache WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    payload_json, expires_at = row
    try:
        expires_dt = dt.datetime.fromisoformat(expires_at)
    except ValueError:
        return None
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=dt.UTC)
    if expires_dt <= dt.datetime.now(dt.UTC):
        return None
    try:
        payload: dict[str, Any] = json.loads(payload_json)
    except json.JSONDecodeError:
        return None
    return payload


def _write_cache(
    db: sqlite3.Connection,
    lat: float,
    lon: float,
    payload: dict[str, Any],
) -> None:
    """Persist a fresh payload with a 1 h TTL (idempotent on cache_key)."""
    key = _cache_key(lat, lon)
    now = dt.datetime.now(dt.UTC)
    expires = now + dt.timedelta(seconds=_CACHE_TTL_SECONDS)
    # Strip the per-call ``cached`` flag from the stored payload — it's set
    # at read time so the caller always knows whether the response came
    # from the wire or from the cache.
    to_store = {k: v for k, v in payload.items() if k != "cached"}
    db.execute(
        "INSERT OR REPLACE INTO weather_cache "
        "(cache_key, payload_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, ?)",
        (key, json.dumps(to_store), now.isoformat(), expires.isoformat()),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Remote fetch
# ---------------------------------------------------------------------------


def _fetch_remote_with_retries(lat: float, lon: float) -> dict[str, Any]:
    """Call Open-Meteo with retries on timeout / 5xx, bubbling up
    ``ServiceUnavailable`` for any permanent failure."""
    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return _fetch_remote_once(lat, lon)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_error = exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            # Retry only on 5xx ; 4xx are permanent.
            if 500 <= status < 600:
                last_error = exc
            else:
                raise ServiceUnavailable("open-meteo", f"returned {status} (no retry)") from exc
        except ValueError as exc:
            # Malformed JSON body — no retry, surface immediately.
            raise ServiceUnavailable("open-meteo", "returned a malformed body") from exc

        if attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))

    raise ServiceUnavailable(
        "open-meteo",
        f"unreachable after {_MAX_RETRIES + 1} attempts",
    ) from last_error


def _fetch_remote_once(lat: float, lon: float) -> dict[str, Any]:
    """One HTTP call to Open-Meteo + payload parsing. Raises HTTPStatusError
    for 4xx/5xx, TimeoutException/NetworkError on transport errors,
    and ValueError for a malformed JSON body."""
    params: dict[str, str | int | float] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pressure_msl",
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,cloud_cover,pressure_msl",
        "past_hours": 6,
        "forecast_hours": 0,
        "wind_speed_unit": "kmh",
    }
    with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
        response = client.get(_OPEN_METEO_URL, params=params)
        response.raise_for_status()
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError("Open-Meteo body is not valid JSON") from exc

    return _parse_payload(data)


# ---------------------------------------------------------------------------
# Payload shaping
# ---------------------------------------------------------------------------


def _parse_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Map the Open-Meteo response into the canonical pechepro dict."""
    current = data.get("current") or {}
    hourly = data.get("hourly") or {}

    pressures_history = [float(p) for p in (hourly.get("pressure_msl") or [])]

    return {
        "temp_air_c": _as_float(current.get("temperature_2m")),
        "pressure_hpa": _as_float(current.get("pressure_msl")),
        "pressure_trend_6h": _compute_trend(pressures_history),
        "pressures_history_hpa": pressures_history,
        "humidity_pct": _as_float(current.get("relative_humidity_2m")),
        "wind_kmh": _as_float(current.get("wind_speed_10m")),
        "cloud_cover_pct": _as_float(current.get("cloud_cover")),
        "fetched_at": dt.datetime.now(dt.UTC).isoformat(),
        "source": _SOURCE,
    }


def _as_float(value: Any) -> float:
    """Coerce to ``float`` ; missing or ``None`` becomes ``0.0``."""
    if value is None:
        return 0.0
    return float(value)


def _compute_trend(pressures: list[float]) -> str:
    """Classify the 6 h pressure trend.

    ``rising`` / ``falling`` / ``steady`` — uses the delta between the first
    and last sample of the window. ``|delta| < 1 hPa`` is considered steady.
    Empty histories return ``"steady"`` as a safe default.
    """
    if len(pressures) < 2:
        return "steady"
    delta = pressures[-1] - pressures[0]
    if abs(delta) < _TREND_STEADY_DELTA_HPA:
        return "steady"
    return "rising" if delta > 0 else "falling"
