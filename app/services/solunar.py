"""solunar — major/minor periods. Plan-2 implements."""

from __future__ import annotations

import datetime as _dt
from typing import Any


def compute_periods(lat: float, lon: float, date: _dt.date) -> dict[str, Any]:
    """Return {'major': [...], 'minor': [...]}. Plan-2 implements."""
    raise NotImplementedError("Implemented in plan-2")
