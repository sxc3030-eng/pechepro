"""usgs_client — water temp from USGS Water Services. Plan-2 implements."""

from __future__ import annotations


def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temp (°C) for nearest USGS station, or None."""
    raise NotImplementedError("Implemented in plan-2")
