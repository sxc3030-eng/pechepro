"""Tests for app.services.baro_analyzer — pressure trend classification."""

from app.services import baro_analyzer

# --------------------------------------------------------------------------- #
# analyze_trend                                                               #
# --------------------------------------------------------------------------- #


def test_analyze_trend_rising_clear() -> None:
    """Pressure rising >= 0.5 hPa over the window returns 'rising'."""
    pressures = [1010.0, 1010.5, 1011.0, 1011.5, 1012.0, 1012.5, 1013.0]
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "rising"


def test_analyze_trend_falling_clear() -> None:
    """Pressure falling >= 0.5 hPa over the window returns 'falling'."""
    pressures = [1015.0, 1014.5, 1014.0, 1013.5, 1013.0, 1012.5, 1012.0]
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "falling"


def test_analyze_trend_steady_within_threshold() -> None:
    """Pressure varying by less than the threshold is steady."""
    pressures = [1013.0, 1013.1, 1013.2, 1013.0, 1012.9, 1013.0, 1013.1]
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "steady"


def test_analyze_trend_empty_list_returns_steady() -> None:
    """Defensive default: empty input -> steady."""
    assert baro_analyzer.analyze_trend([], hours_window=6) == "steady"


def test_analyze_trend_single_point_returns_steady() -> None:
    """Single data point cannot show a trend."""
    assert baro_analyzer.analyze_trend([1013.0], hours_window=6) == "steady"


def test_analyze_trend_all_same_returns_steady() -> None:
    """All identical samples -> zero delta -> steady."""
    pressures = [1013.0] * 7
    assert baro_analyzer.analyze_trend(pressures, hours_window=6) == "steady"


def test_analyze_trend_two_points_rising() -> None:
    """Two-point series with a delta at or above threshold still classifies."""
    assert baro_analyzer.analyze_trend([1010.0, 1011.0]) == "rising"


def test_analyze_trend_two_points_falling() -> None:
    assert baro_analyzer.analyze_trend([1014.0, 1013.0]) == "falling"


def test_analyze_trend_exact_threshold_rising() -> None:
    """Delta exactly at the +threshold counts as rising (inclusive bound)."""
    # delta = +0.5 hPa exactly
    pressures = [1013.0, 1013.5]
    assert baro_analyzer.analyze_trend(pressures) == "rising"


def test_analyze_trend_exact_threshold_falling() -> None:
    """Delta exactly at the -threshold counts as falling (inclusive bound)."""
    pressures = [1013.5, 1013.0]
    assert baro_analyzer.analyze_trend(pressures) == "falling"


def test_analyze_trend_default_hours_window() -> None:
    """Default hours_window=6 works without explicit kwarg."""
    pressures = [1010.0, 1010.5, 1011.0, 1011.5, 1012.0, 1012.5, 1013.0]
    assert baro_analyzer.analyze_trend(pressures) == "rising"
