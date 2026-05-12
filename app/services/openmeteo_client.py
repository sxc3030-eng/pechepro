"""openmeteo_client — wrapper around api.open-meteo.com. Plan-2 implements."""

from __future__ import annotations

import sqlite3
from typing import Any


def get_weather(lat: float, lon: float, db: sqlite3.Connection | None = None) -> dict[str, Any]:
    """Return a weather dict. Plan-2 implements.

    Canonical signature: db param is optional cache backend (weather_cache, TTL 1h).
    Raises ServiceUnavailable on timeout / 5xx after retries.
    """
    raise NotImplementedError("Implemented in plan-2")
