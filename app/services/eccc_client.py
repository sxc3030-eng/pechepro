"""eccc_client — water temp from ECCC Canada. Plan-2 implements."""

from __future__ import annotations


def get_water_temp(lat: float, lon: float) -> float | None:
    """Return water temp (°C) for nearest ECCC station, or None."""
    raise NotImplementedError("Implemented in plan-2")
