"""Barometric pressure analysis: trend detection + species activity scoring.

Public API (canonical, locked in
docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md):

    analyze_trend(pressures_hpa: list[float], hours_window: int = 6) -> str
    species_activity_score(
        db: sqlite3.Connection, species_id: int, baro_trend: str
    ) -> int
"""

from __future__ import annotations

import sqlite3

# Threshold in hPa over the window to qualify as rising/falling.
# Spec §11 mitigation: 6h delta >= 0.5 hPa is the operational rule.
_TREND_THRESHOLD_HPA = 0.5

_VALID_TRENDS = frozenset({"rising", "falling", "steady"})
_DEFAULT_SCORE = 5


def analyze_trend(pressures_hpa: list[float], hours_window: int = 6) -> str:
    """Classify a hourly-sampled pressure series as rising / falling / steady.

    Args:
        pressures_hpa: ordered list of pressure samples in hPa (oldest -> newest).
            Open-Meteo returns evenly-spaced hourly samples, so we treat the
            first and last entries of the window as the start and end of the
            interval being analyzed.
        hours_window: nominal length of the analysis window in hours. Kept as
            a parameter so callers (and future tuning) can reason about it,
            though the math depends on the actual list endpoints rather than
            the index count.

    Returns:
        One of ``"rising"``, ``"falling"`` or ``"steady"``. Defensive default
        ``"steady"`` for empty input or a single sample.
    """
    if not pressures_hpa or len(pressures_hpa) < 2:
        return "steady"

    delta = pressures_hpa[-1] - pressures_hpa[0]
    if delta >= _TREND_THRESHOLD_HPA:
        return "rising"
    if delta <= -_TREND_THRESHOLD_HPA:
        return "falling"
    return "steady"


def species_activity_score(db: sqlite3.Connection, species_id: int, baro_trend: str) -> int:
    """Look up the 1-10 activity score for a (species, baro trend) pair.

    Args:
        db: open SQLite connection with the ``baro_rules`` schema applied.
        species_id: foreign key to ``species.id``.
        baro_trend: one of ``"rising"``, ``"falling"`` or ``"steady"``.

    Returns:
        Integer in ``[1, 10]`` taken from ``baro_rules.activity_score`` when a
        row matches, otherwise the neutral default ``5``.

    Raises:
        ValueError: when ``baro_trend`` is not one of the three valid values.
    """
    if baro_trend not in _VALID_TRENDS:
        raise ValueError(f"baro_trend must be one of {sorted(_VALID_TRENDS)!r}, got {baro_trend!r}")

    row = db.execute(
        "SELECT activity_score FROM baro_rules " "WHERE species_id = ? AND baro_trend = ? LIMIT 1",
        (species_id, baro_trend),
    ).fetchone()
    if row is None:
        return _DEFAULT_SCORE
    return int(row[0])
