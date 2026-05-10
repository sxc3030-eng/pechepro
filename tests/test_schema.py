"""Verify schema.sql is valid and creates the expected tables."""

import sqlite3

EXPECTED_TABLES = {
    "species",
    "regions",
    "water_types",
    "lures",
    "color_visibility",
    "tips",
    "solunar_rules",
    "baro_rules",
    "weather_cache",
    "user_prefs",
    "data_sync_meta",
}


def test_schema_creates_all_expected_tables(empty_db: sqlite3.Connection) -> None:
    rows = empty_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    actual = {row[0] for row in rows}
    missing = EXPECTED_TABLES - actual
    assert not missing, f"Missing tables: {missing}"


def test_schema_indexes_present(empty_db: sqlite3.Connection) -> None:
    rows = empty_db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
    ).fetchall()
    actual = {row[0] for row in rows}
    expected_indexes = {
        "idx_regions_iso",
        "idx_color_visibility_lookup",
        "idx_tips_species",
        "idx_tips_lookup",
    }
    missing = expected_indexes - actual
    assert not missing, f"Missing indexes: {missing}"


def test_regions_country_check_constraint(empty_db: sqlite3.Connection) -> None:
    """country IN ('CA','US','MX') must be enforced."""
    # Valid value should succeed
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    empty_db.commit()
    # Bad country value should fail CHECK
    try:
        empty_db.execute(
            "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
            "VALUES (2, 'Test', 'Test', 'XX', 'TT')"
        )
        empty_db.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("Expected IntegrityError on country='XX'")


def test_tips_confidence_range(empty_db: sqlite3.Connection) -> None:
    """confidence must be 1-5."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (1, 'Doré', 'Walleye', 'Sander vitreus')"
    )
    empty_db.commit()
    # Valid confidence
    empty_db.execute(
        "INSERT INTO tips (id, species_id, tip_text_fr, tip_text_en, confidence) "
        "VALUES (1, 1, 'test', 'test', 3)"
    )
    empty_db.commit()
    # Invalid confidence (out of range)
    try:
        empty_db.execute(
            "INSERT INTO tips (id, species_id, tip_text_fr, tip_text_en, confidence) "
            "VALUES (2, 1, 'test', 'test', 10)"
        )
        empty_db.commit()
    except sqlite3.IntegrityError:
        return
    raise AssertionError("Expected IntegrityError on confidence=10")
