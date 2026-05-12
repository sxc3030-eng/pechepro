"""Header/row-count/enum integrity tests for curated CSVs.

Each CSV under `data/curated/` is checked for:
- correct headers (matching schema columns)
- minimum row counts per spec §3.5 + plan-3 directive
- no duplicate primary-key IDs
- valid enum values where schema CHECK constraints exist
- foreign-key references resolve (within same dataset)
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CURATED = REPO_ROOT / "data" / "curated"


def _load(name: str) -> list[dict[str, str]]:
    path = CURATED / name
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------- species.csv ----------
def test_species_csv_exists_and_has_15_rows() -> None:
    rows = _load("species.csv")
    assert len(rows) == 15, f"expected 15 species, got {len(rows)}"


def test_species_headers_match_schema() -> None:
    rows = _load("species.csv")
    expected = {
        "id",
        "common_name_fr",
        "common_name_en",
        "scientific_name",
        "family",
        "typical_habitat",
        "image_url",
    }
    assert set(rows[0].keys()) >= expected


def test_species_ids_unique() -> None:
    rows = _load("species.csv")
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate species ids"


# ---------- regions.csv ----------
def test_regions_csv_at_least_65_rows() -> None:
    rows = _load("regions.csv")
    assert len(rows) >= 65, f"expected ≥65 regions, got {len(rows)}"


def test_regions_headers_match_schema() -> None:
    rows = _load("regions.csv")
    expected = {
        "id",
        "name_fr",
        "name_en",
        "country",
        "iso_code",
        "bbox_lat_min",
        "bbox_lat_max",
        "bbox_lon_min",
        "bbox_lon_max",
    }
    assert set(rows[0].keys()) >= expected


def test_regions_country_enum_valid() -> None:
    rows = _load("regions.csv")
    allowed = {"CA", "US", "MX"}
    for r in rows:
        assert r["country"] in allowed, f"bad country {r['country']!r} on region {r['id']}"


def test_regions_ids_unique() -> None:
    rows = _load("regions.csv")
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))


# ---------- water_types.csv ----------
def test_water_types_csv_has_5_rows() -> None:
    rows = _load("water_types.csv")
    assert len(rows) == 5


def test_water_types_headers_match_schema() -> None:
    rows = _load("water_types.csv")
    assert set(rows[0].keys()) >= {"id", "name_fr", "name_en"}


# ---------- lures.csv ----------
def test_lures_csv_at_least_30_rows() -> None:
    rows = _load("lures.csv")
    assert len(rows) >= 30, f"expected ≥30 lures, got {len(rows)}"


def test_lures_categories_present() -> None:
    rows = _load("lures.csv")
    cats = {r["category"] for r in rows}
    # Must include the major buckets requested in plan-3
    for needed in {"soft_plastic", "crankbait", "jig", "spinnerbait", "fly"}:
        assert needed in cats, f"missing category {needed!r}"


def test_lures_ids_unique() -> None:
    rows = _load("lures.csv")
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))


# ---------- color_visibility.csv ----------
def test_color_visibility_at_least_120_rows() -> None:
    rows = _load("color_visibility.csv")
    assert len(rows) >= 120, f"expected ≥120 rows, got {len(rows)}"


def test_color_visibility_enums_valid() -> None:
    rows = _load("color_visibility.csv")
    clarities = {"clear", "stained", "muddy"}
    lights = {"bright", "overcast", "dawn_dusk", "night"}
    for r in rows:
        assert r["water_clarity"] in clarities
        assert r["light_level"] in lights
        score = int(r["visibility_score"])
        assert 1 <= score <= 10


# ---------- tips.csv ----------
def test_tips_csv_at_least_300_rows() -> None:
    rows = _load("tips.csv")
    assert len(rows) >= 300, f"expected ≥300 tips, got {len(rows)}"


def test_tips_enums_valid() -> None:
    rows = _load("tips.csv")
    seasons = {"spring", "summer", "fall", "winter", "any"}
    baros = {"rising", "falling", "steady", "any"}
    moons = {"new", "waxing", "full", "waning", "any"}
    tods = {"dawn", "morning", "midday", "afternoon", "dusk", "night", "any"}
    for r in rows:
        assert r["season"] in seasons, f"bad season on tip {r['id']}"
        assert r["baro_trend"] in baros, f"bad baro on tip {r['id']}"
        assert r["moon_phase"] in moons, f"bad moon on tip {r['id']}"
        assert r["time_of_day"] in tods, f"bad time_of_day on tip {r['id']}"
        c = int(r["confidence"])
        assert 1 <= c <= 5, f"bad confidence on tip {r['id']}"


def test_tips_have_bilingual_text() -> None:
    rows = _load("tips.csv")
    for r in rows:
        assert r["tip_text_fr"].strip(), f"empty FR text on tip {r['id']}"
        assert r["tip_text_en"].strip(), f"empty EN text on tip {r['id']}"


def test_tips_species_fk_resolves() -> None:
    species = {r["id"] for r in _load("species.csv")}
    for r in _load("tips.csv"):
        assert r["species_id"] in species, f"unknown species_id {r['species_id']} on tip {r['id']}"


def test_tips_ids_unique() -> None:
    ids = [r["id"] for r in _load("tips.csv")]
    assert len(ids) == len(set(ids))


# ---------- solunar_rules.csv ----------
def test_solunar_rules_has_4_rows() -> None:
    rows = _load("solunar_rules.csv")
    assert len(rows) == 4


def test_solunar_rules_period_types() -> None:
    rows = _load("solunar_rules.csv")
    types = [r["period_type"] for r in rows]
    assert "major" in types
    assert "minor" in types
    for r in rows:
        assert r["period_type"] in {"major", "minor"}
        w = float(r["weight"])
        assert 0.0 <= w <= 1.0


# ---------- baro_rules.csv ----------
def test_baro_rules_csv_has_45_rows() -> None:
    rows = _load("baro_rules.csv")
    assert len(rows) == 45, f"expected 45 rows (15 species × 3 trends), got {len(rows)}"


def test_baro_rules_covers_all_species_x_trends() -> None:
    rows = _load("baro_rules.csv")
    pairs = {(r["species_id"], r["baro_trend"]) for r in rows}
    species_ids = {r["id"] for r in _load("species.csv")}
    for sid in species_ids:
        for trend in ("rising", "falling", "steady"):
            assert (sid, trend) in pairs, f"missing baro_rule for species={sid} trend={trend}"


def test_baro_rules_activity_scores_in_range() -> None:
    for r in _load("baro_rules.csv"):
        s = int(r["activity_score"])
        assert 1 <= s <= 10, f"score out of range on baro_rule {r['id']}"


def test_baro_rules_bilingual_notes() -> None:
    for r in _load("baro_rules.csv"):
        assert r["notes_fr"].strip()
        assert r["notes_en"].strip()


# ---------- safety ----------
@pytest.mark.parametrize(
    "name",
    [
        "species.csv",
        "regions.csv",
        "water_types.csv",
        "lures.csv",
        "color_visibility.csv",
        "tips.csv",
        "solunar_rules.csv",
        "baro_rules.csv",
    ],
)
def test_csv_uses_utf8_bom(name: str) -> None:
    """All curated CSVs are UTF-8 with BOM per plan-3 directive."""
    with (CURATED / name).open("rb") as fh:
        first3 = fh.read(3)
    assert first3 == b"\xef\xbb\xbf", f"{name} missing UTF-8 BOM"
