"""Barometric pressure analysis: trend detection.

Public API (canonical, locked in
docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md):

    analyze_trend(pressures_hpa: list[float], hours_window: int = 6) -> str
"""

from __future__ import annotations

# Threshold in hPa over the window to qualify as rising/falling.
# Spec §11 mitigation: 6h delta >= 0.5 hPa is the operational rule.
_TREND_THRESHOLD_HPA = 0.5


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
