"""Geolocation: Windows Location API first, fallback to IP geolocation via ipapi.co.

Public API is sync (per cross-plan amendments: Flask 3 routes are sync by default).
The winsdk path wraps an async call with ``asyncio.run`` internally.

Tests must mock ``_query_windows_location`` (and/or ``_query_ip_location``) directly
- winsdk is Windows-only so the suite must run on Linux CI without it installed.
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

    Strategy:
      1. Windows Location API via ``winsdk.windows.devices.geolocation`` (only on win32;
         requires user to grant location permission; may raise / return None if denied).
      2. Fallback to IP geolocation via ipapi.co (free, 1000 req/day, no key).
         URL: https://ipapi.co/json/ - returns ``{"latitude": ..., "longitude": ..., ...}``.
      3. If both fail, return None.

    Returns:
        (lat, lon) tuple of floats, or None if no source could resolve a position.
    """
    if sys.platform == "win32":
        try:
            result = _query_windows_location()
            if result is not None:
                return result
        except Exception as exc:
            logger.warning("Windows Location API failed: %s", exc)

    try:
        return _query_ip_location()
    except Exception as exc:
        logger.warning("IP geolocation failed: %s", exc)
        return None


def _query_windows_location() -> tuple[float, float] | None:  # pragma: no cover
    """Call winsdk to get the current position.

    Synchronous wrapper around the async ``get_geoposition_async()`` API. Returns None
    if no position is available; raises on permission denial or missing winsdk install.

    Excluded from coverage: tests mock this function at the module boundary so the
    body never executes, and Linux CI has no ``winsdk`` install. Covered indirectly
    through manual on-Windows verification.
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
    """Fallback: ipapi.co returns lat/lon based on the caller IP.

    Returns None on non-200 responses or when the payload lacks coordinates.
    """
    response = httpx.get(_IPAPI_URL, timeout=_TIMEOUT_SECONDS)
    if response.status_code != 200:
        return None
    data = response.json()
    lat = data.get("latitude")
    lon = data.get("longitude")
    if lat is None or lon is None:
        return None
    return (float(lat), float(lon))
