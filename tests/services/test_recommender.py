"""Tests for app.services.recommender — tip ranking with hierarchical fallback."""

from __future__ import annotations

import sqlite3
import time

import pytest

from app.services import recommender

# ---------------------------------------------------------------------------
# Fixture seed helpers
# ---------------------------------------------------------------------------


def _seed_recommender_fixture(db: sqlite3.Connection) -> None:
    """Seed minimal data: 1 species (walleye=3), 1 region (QC=1), 1 water_type (lake=1).

    Inserts 5 tips of varying specificity:
      - tip 1: exact match all conditions (Tier-1, highest score)
      - tip 2: matches species+region only (Tier-1, generic conditions)
      - tip 3: generic species (region NULL, water_type NULL) — Tier-3 fallback
      - tip 4: completely different species (filtered out)
      - tip 5: same species but different region_id (filtered out)
    """
    db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (5, 'Brochet', 'Northern Pike', 'Esox lucius')"
    )
    db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (2, 'Ontario', 'Ontario', 'CA', 'ON')"
    )
    db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")

    # Note: column order: species_id, region_id, water_type_id, season, baro_trend,
    # moon_phase, temp_water_min_c, temp_water_max_c, time_of_day, tip_text_fr,
    # tip_text_en, source_url, confidence
    tips = [
        # tip 1: full match (Tier-1 exact)
        (
            3,
            1,
            1,
            "summer",
            "falling",
            "full",
            None,
            None,
            "any",
            "Match parfait",
            "Perfect match",
            "https://example.com/1",
            5,
        ),
        # tip 2: species + region match, generic baro/moon (Tier-1, less specific)
        (
            3,
            1,
            1,
            "any",
            "any",
            "any",
            None,
            None,
            "any",
            "Match région",
            "Region match",
            "https://example.com/2",
            4,
        ),
        # tip 3: generic species (region NULL, water_type NULL) — Tier-3
        (
            3,
            None,
            None,
            "any",
            "any",
            "any",
            None,
            None,
            "any",
            "Conseil générique",
            "Generic tip",
            "https://example.com/3",
            3,
        ),
        # tip 4: wrong species (filtered)
        (
            5,
            1,
            1,
            "summer",
            "falling",
            "full",
            None,
            None,
            "any",
            "Pas pour walleye",
            "Not for walleye",
            "https://example.com/4",
            5,
        ),
        # tip 5: right species, wrong region (filtered)
        (
            3,
            2,
            1,
            "summer",
            "falling",
            "full",
            None,
            None,
            "any",
            "Mauvaise région",
            "Wrong region",
            "https://example.com/5",
            5,
        ),
    ]
    db.executemany(
        "INSERT INTO tips (species_id, region_id, water_type_id, season, baro_trend, "
        "moon_phase, temp_water_min_c, temp_water_max_c, time_of_day, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        tips,
    )
    db.commit()


# ---------------------------------------------------------------------------
# Task 13 : exact match happy path
# ---------------------------------------------------------------------------


def test_recommend_returns_exact_match_first(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    assert len(result) >= 1
    assert result[0]["tip_text_fr"] == "Match parfait"
    assert result[0]["confidence"] == 5
    # Match score should reflect # of matched conditions
    if len(result) > 1:
        assert result[0]["match_score"] >= result[1]["match_score"]


def test_recommend_excludes_other_species(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    texts = {tip["tip_text_fr"] for tip in result}
    assert "Pas pour walleye" not in texts


def test_recommend_excludes_wrong_region_when_region_specified(
    empty_db: sqlite3.Connection,
) -> None:
    """When region_id is specified, tips with a different non-null region_id are excluded.
    Tips with region_id=NULL are still allowed (generic fallback)."""
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    texts = {tip["tip_text_fr"] for tip in result}
    assert "Mauvaise région" not in texts


def test_recommend_returns_at_most_limit(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
        limit=2,
    )
    assert len(result) <= 2


def test_recommend_limit_three_returns_only_three(empty_db: sqlite3.Connection) -> None:
    """Limit respected: limit=3 returns at most 3 tips even when more match."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander vitreus')"
    )
    # 6 generic tips for species 3
    for i in range(6):
        empty_db.execute(
            "INSERT INTO tips (species_id, tip_text_fr, tip_text_en, source_url, "
            "confidence) VALUES (3, ?, ?, NULL, ?)",
            (f"tip {i}", f"tip {i}", (i % 5) + 1),
        )
    empty_db.commit()
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={"baro_trend": "falling"},
        limit=3,
    )
    assert len(result) == 3


def test_recommend_returns_required_fields(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    assert result, "expected at least one tip"
    expected_keys = {"id", "tip_text_fr", "tip_text_en", "source_url", "confidence", "match_score"}
    assert expected_keys <= set(result[0].keys())


def test_recommend_match_score_is_float_between_zero_and_one(empty_db: sqlite3.Connection) -> None:
    """match_score is a float in [0.0, 1.0] (with tier_bonus capped at 1.0)."""
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full", "season": "summer"},
    )
    for tip in result:
        assert isinstance(tip["match_score"], float)
        assert 0.0 <= tip["match_score"] <= 1.0


# ---------------------------------------------------------------------------
# Task 14 : hierarchical fallback
# ---------------------------------------------------------------------------


def test_recommend_falls_back_to_generic_when_no_specific(empty_db: sqlite3.Connection) -> None:
    """If only generic (region=NULL) tips exist, they are returned anyway."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, tip_text_en, "
        "source_url, confidence) VALUES (3, NULL, NULL, 'Générique', 'Generic', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    assert len(result) == 1
    assert result[0]["tip_text_fr"] == "Générique"


def test_recommend_returns_empty_when_species_unknown(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=999,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    assert result == []


def test_recommend_empty_db_returns_empty_list(empty_db: sqlite3.Connection) -> None:
    """No tips at all → returns empty list (not None)."""
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling"},
    )
    assert result == []


def test_recommend_no_region_id_returns_all_species_tips(empty_db: sqlite3.Connection) -> None:
    """When region_id=None, all tips for the species are eligible."""
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 20.0,
        },
    )
    texts = {t["tip_text_fr"] for t in result}
    assert "Mauvaise région" in texts  # now allowed since no region filter
    assert "Pas pour walleye" not in texts  # still wrong species


# ---------------------------------------------------------------------------
# Hierarchical tier system (T1 / T2 / T3 with bonus + stop-at-≥3-T1 rule)
# ---------------------------------------------------------------------------


def test_recommend_tier1_bonus_outranks_tier3(empty_db: sqlite3.Connection) -> None:
    """A Tier-1 tip (exact species+region+water) should outrank a Tier-3 generic tip
    with the same condition match count, thanks to tier_bonus."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'QC', 'QC', 'CA', 'QC')"
    )
    empty_db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    # T1: exact match on region+water
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, season, baro_trend, "
        "moon_phase, tip_text_fr, tip_text_en, source_url, confidence) "
        "VALUES (3, 1, 1, 'summer', 'falling', 'full', 'T1 tip', 'T1', NULL, 3)"
    )
    # T3: generic species (region NULL, water_type NULL)
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, season, baro_trend, "
        "moon_phase, tip_text_fr, tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, NULL, 'summer', 'falling', 'full', 'T3 tip', 'T3', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling", "moon_phase": "full", "season": "summer"},
    )
    assert result[0]["tip_text_fr"] == "T1 tip"
    # Tier-1 should score higher than Tier-3 with same condition matches
    t1_score = next(t["match_score"] for t in result if t["tip_text_fr"] == "T1 tip")
    t3_score = next(t["match_score"] for t in result if t["tip_text_fr"] == "T3 tip")
    assert t1_score > t3_score


def test_recommend_zero_tier1_falls_through_to_tier2(empty_db: sqlite3.Connection) -> None:
    """Hierarchical fallback: 0 Tier-1 tips → Tier-2 (region_id NULL) tips returned."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'QC', 'QC', 'CA', 'QC')"
    )
    empty_db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    # No T1 tips (no tip with region_id=1)
    # T2 tip: region_id NULL, water_type_id=1
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, 1, 'T2 tip', 'T2', NULL, 4)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling"},
    )
    assert len(result) == 1
    assert result[0]["tip_text_fr"] == "T2 tip"


def test_recommend_few_tier1_includes_tier2(empty_db: sqlite3.Connection) -> None:
    """With <3 Tier-1 tips, Tier-2 tips also get included to broaden recommendations."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'QC', 'QC', 'CA', 'QC')"
    )
    empty_db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    # 1 T1 tip (region=1, water_type=1)
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 1, 1, 'T1 lone', 'T1', NULL, 5)"
    )
    # 2 T2 tips (region NULL)
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, 1, 'T2 a', 'T2 a', NULL, 4)"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, 1, 'T2 b', 'T2 b', NULL, 4)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling"},
    )
    texts = {t["tip_text_fr"] for t in result}
    # Only 1 T1, so T2 tips should be included
    assert "T1 lone" in texts
    assert "T2 a" in texts
    assert "T2 b" in texts


def test_recommend_many_tier1_stops_there(empty_db: sqlite3.Connection) -> None:
    """If Tier-1 returns ≥3 tips, Tier-2 / Tier-3 are NOT added (focus stays specific)."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'QC', 'QC', 'CA', 'QC')"
    )
    empty_db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    # 3 Tier-1 tips (region=1, water_type=1)
    for i in range(3):
        empty_db.execute(
            "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
            "tip_text_en, source_url, confidence) "
            "VALUES (3, 1, 1, ?, ?, NULL, 4)",
            (f"T1 #{i}", f"T1 #{i}"),
        )
    # Plenty of T2/T3 backups that should NOT appear
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, 1, 'T2 should be hidden', 'T2', NULL, 5)"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, NULL, 'T3 should be hidden', 'T3', NULL, 5)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling"},
    )
    texts = {t["tip_text_fr"] for t in result}
    assert "T2 should be hidden" not in texts
    assert "T3 should be hidden" not in texts
    # All 3 Tier-1 tips present
    for i in range(3):
        assert f"T1 #{i}" in texts


def test_recommend_temp_range_match_boosts_score(empty_db: sqlite3.Connection) -> None:
    """A tip with water-temp range matching user's temp should outrank one without."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    # Tip A: temp range matches
    empty_db.execute(
        "INSERT INTO tips (species_id, temp_water_min_c, temp_water_max_c, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 18.0, 22.0, 'Match temp', 'Temp match', NULL, 3)"
    )
    # Tip B: no temp range (generic)
    empty_db.execute(
        "INSERT INTO tips (species_id, temp_water_min_c, temp_water_max_c, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, NULL, NULL, 'No temp', 'No temp', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={"water_temp_c": 20.0},
    )
    assert result[0]["tip_text_fr"] == "Match temp"


# ---------------------------------------------------------------------------
# Task 23 : deterministic tie-breaking + limit=0
# ---------------------------------------------------------------------------


def test_recommend_same_score_orders_by_confidence_then_id(
    empty_db: sqlite3.Connection,
) -> None:
    """Two tips with identical match_score: higher confidence first; ties broken by id ASC."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    rows = [
        # (id, species_id, tip_fr, tip_en, confidence)
        (1, 3, "Tip A", "Tip A", 4),
        (2, 3, "Tip B", "Tip B", 5),  # higher confidence — should come first
        (3, 3, "Tip C", "Tip C", 4),
    ]
    for tid, sid, fr, en, conf in rows:
        empty_db.execute(
            "INSERT INTO tips (id, species_id, tip_text_fr, tip_text_en, source_url, "
            "confidence) VALUES (?, ?, ?, ?, NULL, ?)",
            (tid, sid, fr, en, conf),
        )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={},
    )
    texts = [t["tip_text_fr"] for t in result]
    assert texts == ["Tip B", "Tip A", "Tip C"]


def test_recommend_limit_zero_returns_empty(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
        },
        limit=0,
    )
    assert result == []


# ---------------------------------------------------------------------------
# Task 32 : validation
# ---------------------------------------------------------------------------


def test_recommend_species_id_none_raises(empty_db: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        recommender.recommend(
            db=empty_db,
            species_id=None,  # type: ignore[arg-type]
            region_id=1,
            water_type_id=1,
            conditions={},
        )


def test_recommend_negative_limit_returns_empty(empty_db: sqlite3.Connection) -> None:
    _seed_recommender_fixture(empty_db)
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=1,
        conditions={"baro_trend": "falling"},
        limit=-5,
    )
    assert result == []


def test_recommend_species_id_bool_raises(empty_db: sqlite3.Connection) -> None:
    """bool is a subclass of int — must be rejected explicitly."""
    with pytest.raises(TypeError):
        recommender.recommend(
            db=empty_db,
            species_id=True,  # type: ignore[arg-type]
            region_id=1,
            water_type_id=1,
            conditions={},
        )


def test_recommend_species_id_string_raises(empty_db: sqlite3.Connection) -> None:
    """Non-int species_id should raise TypeError."""
    with pytest.raises(TypeError):
        recommender.recommend(
            db=empty_db,
            species_id="walleye",  # type: ignore[arg-type]
            region_id=1,
            water_type_id=1,
            conditions={},
        )


def test_recommend_region_without_water_type(empty_db: sqlite3.Connection) -> None:
    """Tier-1 query when region_id is set but water_type_id is None — exercises
    the Tier-1 branch without the water_type soft filter."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'QC', 'QC', 'CA', 'QC')"
    )
    empty_db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    empty_db.execute(
        "INSERT INTO water_types (id, name_fr, name_en) VALUES (2, 'Rivière', 'River')"
    )
    # 3 Tier-1 tips with mixed water_type values — all should appear
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 1, NULL, 'no water_type', 'no wt', NULL, 4)"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 1, 1, 'lake', 'lake', NULL, 4)"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, region_id, water_type_id, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 1, 2, 'river', 'river', NULL, 4)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=1,
        water_type_id=None,
        conditions={"baro_trend": "falling"},
    )
    texts = {t["tip_text_fr"] for t in result}
    assert texts == {"no water_type", "lake", "river"}


def test_recommend_handles_non_numeric_water_temp_gracefully(
    empty_db: sqlite3.Connection,
) -> None:
    """A garbage water_temp_c value (e.g. user-side bug) shouldn't crash."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, temp_water_min_c, temp_water_max_c, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 18.0, 22.0, 'Range', 'Range', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={"water_temp_c": "warm"},  # garbage string
    )
    assert len(result) == 1
    # Score should still be valid (the temp condition just doesn't match)
    assert 0.0 <= result[0]["match_score"] <= 1.0


# ---------------------------------------------------------------------------
# Confidence weight in score (task instructions rule 6)
# ---------------------------------------------------------------------------


def test_recommend_confidence_weighted_in_score(empty_db: sqlite3.Connection) -> None:
    """Two tips matching identical conditions: confidence=5 outranks confidence=1
    (confidence contributes 0.3 weight in match_score)."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO tips (id, species_id, baro_trend, tip_text_fr, tip_text_en, "
        "source_url, confidence) "
        "VALUES (1, 3, 'falling', 'High conf', 'High', NULL, 5)"
    )
    empty_db.execute(
        "INSERT INTO tips (id, species_id, baro_trend, tip_text_fr, tip_text_en, "
        "source_url, confidence) "
        "VALUES (2, 3, 'falling', 'Low conf', 'Low', NULL, 1)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={"baro_trend": "falling"},
    )
    assert result[0]["tip_text_fr"] == "High conf"
    high_score = result[0]["match_score"]
    low_score = result[1]["match_score"]
    assert high_score > low_score


# ---------------------------------------------------------------------------
# Conditions 'any' value or absent — score adjusts (task instructions rule 5)
# ---------------------------------------------------------------------------


def test_recommend_conditions_absent_handled_gracefully(empty_db: sqlite3.Connection) -> None:
    """Missing condition keys do not crash; tip 'any' values match user values."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, baro_trend, moon_phase, season, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (3, 'any', 'any', 'any', 'Universal', 'Universal', NULL, 3)"
    )
    empty_db.commit()

    # Empty conditions dict
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={},
    )
    assert len(result) == 1
    assert result[0]["tip_text_fr"] == "Universal"
    assert isinstance(result[0]["match_score"], float)


def test_recommend_conditions_with_any_value(empty_db: sqlite3.Connection) -> None:
    """User condition value == 'any' — should be treated as a soft match against tip values."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, baro_trend, tip_text_fr, tip_text_en, "
        "source_url, confidence) "
        "VALUES (3, 'falling', 'Specific', 'Specific', NULL, 4)"
    )
    empty_db.commit()

    # User passes 'any' — should not crash and should return the tip
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={"baro_trend": "any"},
    )
    assert len(result) == 1
    assert result[0]["tip_text_fr"] == "Specific"


# ---------------------------------------------------------------------------
# Task 40 : 1k-tip performance smoke
# ---------------------------------------------------------------------------


def test_recommend_handles_1000_tips_under_500ms(empty_db: sqlite3.Connection) -> None:
    """Performance smoke: 1000 tips for a single species should complete fast."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    rows = []
    for i in range(1000):
        rows.append(
            (
                3,
                None,
                None,
                "any",
                "any",
                "any",
                None,
                None,
                "any",
                f"Tip FR {i}",
                f"Tip EN {i}",
                None,
                (i % 5) + 1,
            )
        )
    empty_db.executemany(
        "INSERT INTO tips (species_id, region_id, water_type_id, season, baro_trend, "
        "moon_phase, temp_water_min_c, temp_water_max_c, time_of_day, tip_text_fr, "
        "tip_text_en, source_url, confidence) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    empty_db.commit()

    start = time.perf_counter()
    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={"baro_trend": "falling", "moon_phase": "full"},
        limit=10,
    )
    elapsed = time.perf_counter() - start

    assert len(result) == 10
    assert elapsed < 0.5, f"Recommender too slow: {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Task 43 : NULL water_type_id semantics
# ---------------------------------------------------------------------------


def test_recommend_water_type_filter_allows_null_tips(empty_db: sqlite3.Connection) -> None:
    """When water_type_id=1 is requested, tips with water_type_id=NULL should still appear
    (NULL is the 'works in any water type' wildcard)."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    empty_db.execute(
        "INSERT INTO water_types (id, name_fr, name_en) VALUES (2, 'Rivière', 'River')"
    )
    # Tip with water_type=1 (specific to lake)
    empty_db.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, 1, 'Lac specific', 'Lake specific', NULL, 4)"
    )
    # Tip with water_type=NULL (works for any water)
    empty_db.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, NULL, 'Toute eau', 'Any water', NULL, 3)"
    )
    # Tip with water_type=2 (river — should be excluded)
    empty_db.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, source_url, "
        "confidence) VALUES (3, 2, 'Rivière specific', 'River specific', NULL, 4)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=1,
        conditions={},
    )
    texts = {t["tip_text_fr"] for t in result}
    assert "Lac specific" in texts
    assert "Toute eau" in texts
    assert "Rivière specific" not in texts


# ---------------------------------------------------------------------------
# Light level + water clarity passthrough (conditions spec'd in canonical docstring)
# ---------------------------------------------------------------------------


def test_recommend_does_not_crash_on_extra_condition_keys(empty_db: sqlite3.Connection) -> None:
    """light_level and water_clarity are valid condition keys per docstring; verify
    that passing them does not crash even if not used in scoring."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré', 'Walleye', 'Sander')"
    )
    empty_db.execute(
        "INSERT INTO tips (species_id, baro_trend, tip_text_fr, tip_text_en, "
        "source_url, confidence) "
        "VALUES (3, 'falling', 'Tip', 'Tip', NULL, 3)"
    )
    empty_db.commit()

    result = recommender.recommend(
        db=empty_db,
        species_id=3,
        region_id=None,
        water_type_id=None,
        conditions={
            "baro_trend": "falling",
            "moon_phase": "full",
            "season": "summer",
            "time_of_day": "morning",
            "water_temp_c": 18.5,
            "water_clarity": "stained",
            "light_level": "overcast",
        },
    )
    assert len(result) == 1
    assert isinstance(result[0]["match_score"], float)
