"""Tests for app.db.init_db — first-run database initialization."""

import csv
import sqlite3
from pathlib import Path

from app.db.init_db import (
    apply_schema,
    default_db_path,
    ensure_database,
    is_db_corrupt,
    load_seed_csvs,
    recover_corrupt_db,
)


def test_apply_schema_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    names = {r[0] for r in rows}
    conn.close()
    assert "species" in names
    assert "tips" in names
    assert "weather_cache" in names
    assert "user_prefs" in names


def test_apply_schema_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    apply_schema(db_path)  # second call must not raise
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchall()
    conn.close()
    assert rows[0][0] >= 11


def test_ensure_database_creates_db_when_absent(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    assert not db_path.exists()
    result = ensure_database(db_path)
    assert db_path.exists()
    assert result is True  # signals first-run


def test_ensure_database_returns_false_when_present(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    result = ensure_database(db_path)
    assert result is False  # not first-run


def test_apply_schema_creates_parent_dir(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "dir" / "p.db"
    apply_schema(nested)
    assert nested.exists()


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow(r)


def test_load_seed_csvs_imports_species(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        [
            "id",
            "common_name_fr",
            "common_name_en",
            "scientific_name",
            "family",
            "typical_habitat",
            "image_url",
        ],
        [
            [1, "Doré jaune", "Walleye", "Sander vitreus", "Percidae", "lac/rivière", ""],
            [2, "Achigan", "Largemouth Bass", "Micropterus salmoides", "Centrarchidae", "lac", ""],
        ],
    )
    counts = load_seed_csvs(db_path, csv_dir)
    assert counts["species"] == 2
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT common_name_fr FROM species ORDER BY id").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["Doré jaune", "Achigan"]


def test_load_seed_csvs_skips_missing_files(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    counts = load_seed_csvs(db_path, tmp_path / "nonexistent")
    assert counts == {}


def test_load_seed_csvs_skips_when_table_already_seeded(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (99, 'Existing', 'Existing', 'Existing')"
    )
    conn.commit()
    conn.close()
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        [
            "id",
            "common_name_fr",
            "common_name_en",
            "scientific_name",
            "family",
            "typical_habitat",
            "image_url",
        ],
        [[1, "Doré jaune", "Walleye", "Sander vitreus", "", "", ""]],
    )
    counts = load_seed_csvs(db_path, csv_dir)
    assert counts.get("species", 0) == 0  # skipped because not empty


def test_load_seed_csvs_loads_all_eight_curated_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        [
            "id",
            "common_name_fr",
            "common_name_en",
            "scientific_name",
            "family",
            "typical_habitat",
            "image_url",
        ],
        [[1, "Doré", "Walleye", "Sander vitreus", "", "", ""]],
    )
    _write_csv(
        csv_dir / "regions.csv",
        [
            "id",
            "name_fr",
            "name_en",
            "country",
            "iso_code",
            "bbox_lat_min",
            "bbox_lat_max",
            "bbox_lon_min",
            "bbox_lon_max",
        ],
        [[1, "Québec", "Quebec", "CA", "QC", 45.0, 62.0, -79.0, -57.0]],
    )
    _write_csv(
        csv_dir / "water_types.csv",
        ["id", "name_fr", "name_en"],
        [[1, "Lac", "Lake"]],
    )
    _write_csv(
        csv_dir / "lures.csv",
        ["id", "name_fr", "name_en", "category", "image_url"],
        [[1, "Tube", "Tube", "soft", ""]],
    )
    _write_csv(
        csv_dir / "color_visibility.csv",
        ["id", "water_clarity", "light_level", "color", "visibility_score", "notes_fr", "notes_en"],
        [[1, "clear", "bright", "white", 9, "", ""]],
    )
    _write_csv(
        csv_dir / "tips.csv",
        [
            "id",
            "species_id",
            "region_id",
            "water_type_id",
            "season",
            "baro_trend",
            "moon_phase",
            "temp_water_min_c",
            "temp_water_max_c",
            "time_of_day",
            "tip_text_fr",
            "tip_text_en",
            "source_url",
            "confidence",
        ],
        [
            [
                1,
                1,
                1,
                1,
                "spring",
                "rising",
                "any",
                8.0,
                14.0,
                "dawn",
                "Tip FR",
                "Tip EN",
                "https://example.com",
                4,
            ]
        ],
    )
    _write_csv(
        csv_dir / "solunar_rules.csv",
        ["id", "period_type", "duration_minutes", "weight"],
        [[1, "major", 120, 1.0], [2, "minor", 60, 0.6]],
    )
    _write_csv(
        csv_dir / "baro_rules.csv",
        ["id", "species_id", "baro_trend", "activity_score", "notes_fr", "notes_en"],
        [[1, 1, "rising", 8, "", ""]],
    )
    counts = load_seed_csvs(db_path, csv_dir)
    assert counts == {
        "species": 1,
        "regions": 1,
        "water_types": 1,
        "lures": 1,
        "color_visibility": 1,
        "tips": 1,
        "solunar_rules": 2,
        "baro_rules": 1,
    }


def test_load_seed_csvs_empty_string_becomes_null(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    csv_dir = tmp_path / "curated"
    _write_csv(
        csv_dir / "species.csv",
        [
            "id",
            "common_name_fr",
            "common_name_en",
            "scientific_name",
            "family",
            "typical_habitat",
            "image_url",
        ],
        [[1, "Doré", "Walleye", "Sander vitreus", "", "", ""]],
    )
    load_seed_csvs(db_path, csv_dir)
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT family, image_url FROM species WHERE id=1").fetchone()
    conn.close()
    assert row[0] is None
    assert row[1] is None


def test_is_db_corrupt_returns_false_for_healthy(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    assert is_db_corrupt(db_path) is False


def test_is_db_corrupt_returns_true_for_garbage_file(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    db_path.write_bytes(b"not a sqlite file")
    assert is_db_corrupt(db_path) is True


def test_is_db_corrupt_returns_false_for_missing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "missing.db"
    # Missing file is not "corrupt" — caller treats it as first-run.
    assert is_db_corrupt(db_path) is False


def test_recover_corrupt_db_replaces_with_fresh_schema(tmp_path: Path) -> None:
    db_path = tmp_path / "p.db"
    db_path.write_bytes(b"corrupt content")
    recover_corrupt_db(db_path)
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='species'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_default_db_path_with_localappdata(monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    p = default_db_path()
    assert "pechepro" in str(p)
    assert str(p).endswith("pechepro.db")


def test_default_db_path_without_localappdata(monkeypatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    p = default_db_path()
    assert str(p).endswith("pechepro.db")
