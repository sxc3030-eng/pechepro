"""astral_calc service — sunrise/sunset/moon phase. Plan-2 implements."""

from __future__ import annotations

import datetime as _dt
from typing import Any


def sun_moon(lat: float, lon: float, date: _dt.date) -> dict[str, Any]:
    """Compute sun + moon data for given location and date.

    Canonical signature locked in cross-plan amendments. Plan-2 implements.
    """
    raise NotImplementedError("Implemented in plan-2")
