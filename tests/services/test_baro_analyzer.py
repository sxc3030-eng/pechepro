"""Tests for app.services.baro_analyzer — pressure trend + species activity scoring."""

import sqlite3

import pytest

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


# --------------------------------------------------------------------------- #
# species_activity_score                                                      #
# --------------------------------------------------------------------------- #


def _seed_baro_rules(db: sqlite3.Connection) -> None:
    """Insert a species + 3 baro_rules rows for testing."""
    db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    db.executemany(
        "INSERT INTO baro_rules (species_id, baro_trend, activity_score, notes_fr, notes_en) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (3, "rising", 6, "Activité modérée", "Moderate activity"),
            (3, "falling", 9, "Pic d'activité", "Peak activity"),
            (3, "steady", 4, "Calme", "Calm"),
        ],
    )
    db.commit()


def test_species_activity_score_returns_db_value(empty_db: sqlite3.Connection) -> None:
    """Each seeded (species, trend) row returns its activity_score."""
    _seed_baro_rules(empty_db)
    assert baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="falling") == 9
    assert baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="rising") == 6
    assert baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="steady") == 4


def test_species_activity_score_no_rule_returns_default(empty_db: sqlite3.Connection) -> None:
    """Unknown species_id returns the neutral default 5."""
    _seed_baro_rules(empty_db)
    assert baro_analyzer.species_activity_score(empty_db, species_id=999, baro_trend="rising") == 5


def test_species_activity_score_partial_rule_returns_default(
    empty_db: sqlite3.Connection,
) -> None:
    """Known species but missing trend row returns the neutral default 5."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (4, 'Achigan', 'Bass', 'Micropterus')"
    )
    empty_db.execute(
        "INSERT INTO baro_rules (species_id, baro_trend, activity_score) " "VALUES (4, 'rising', 7)"
    )
    empty_db.commit()
    assert baro_analyzer.species_activity_score(empty_db, species_id=4, baro_trend="falling") == 5


def test_species_activity_score_invalid_trend_raises(empty_db: sqlite3.Connection) -> None:
    """Trend not in {rising, falling, steady} raises ValueError."""
    _seed_baro_rules(empty_db)
    with pytest.raises(ValueError):
        baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="bogus")


def test_species_activity_score_empty_string_trend_raises(
    empty_db: sqlite3.Connection,
) -> None:
    """Empty trend string is invalid."""
    with pytest.raises(ValueError):
        baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="")


def test_species_activity_score_returns_int_type(empty_db: sqlite3.Connection) -> None:
    """Return type is int, not sqlite3 row tuple."""
    _seed_baro_rules(empty_db)
    result = baro_analyzer.species_activity_score(empty_db, species_id=3, baro_trend="rising")
    assert isinstance(result, int)
