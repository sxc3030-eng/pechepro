"""Coverage tests for tips.csv per plan-3 directive."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

CURATED = Path(__file__).resolve().parents[2] / "data" / "curated"


def _load(name: str) -> list[dict[str, str]]:
    with (CURATED / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def test_at_least_18_tips_per_species() -> None:
    tips = _load("tips.csv")
    species_ids = [r["id"] for r in _load("species.csv")]
    per = Counter(t["species_id"] for t in tips)
    missing = {sid: per.get(sid, 0) for sid in species_ids if per.get(sid, 0) < 18}
    assert not missing, f"species below 18 tips: {missing}"


def test_mix_of_regional_and_global_tips() -> None:
    tips = _load("tips.csv")
    regional = [t for t in tips if t["region_id"] not in (None, "")]
    global_ = [t for t in tips if t["region_id"] in (None, "")]
    assert len(regional) >= 30, f"need ≥30 region-specific tips, got {len(regional)}"
    assert len(global_) >= 30, f"need ≥30 global tips, got {len(global_)}"


def test_every_species_season_combo_has_at_least_one_tip() -> None:
    """For each species × season (spring/summer/fall/winter) at least 1 tip exists.

    'any' season counts as covering all four because the recommender falls back
    to it. So a species needs either a season-specific row or an 'any' row per
    season slot. We check the species has at least 1 of (season-specific OR any).
    """
    tips = _load("tips.csv")
    species_ids = [r["id"] for r in _load("species.csv")]
    grouped: dict[str, set[str]] = defaultdict(set)
    for t in tips:
        grouped[t["species_id"]].add(t["season"])
    missing: dict[str, list[str]] = {}
    for sid in species_ids:
        seasons = grouped[sid]
        if "any" in seasons:
            continue
        gap = [s for s in ("spring", "summer", "fall", "winter") if s not in seasons]
        if gap:
            missing[sid] = gap
    assert not missing, f"species missing season coverage: {missing}"


def test_high_confidence_tips_have_source() -> None:
    """Tips with confidence ≥ 3 must cite a source_url (per plan-3 §Data Quality)."""
    tips = _load("tips.csv")
    bad = [t["id"] for t in tips if int(t["confidence"]) >= 3 and not t["source_url"].strip()]
    assert not bad, f"high-confidence tips missing source_url: {bad[:10]}"


def test_tactic_diversity_per_species() -> None:
    """Each species should have tips across multiple baro trends (signal of breadth)."""
    tips = _load("tips.csv")
    species_ids = [r["id"] for r in _load("species.csv")]
    per: dict[str, set[str]] = defaultdict(set)
    for t in tips:
        per[t["species_id"]].add(t["baro_trend"])
    thin = {sid: per.get(sid, set()) for sid in species_ids if len(per.get(sid, set())) < 2}
    assert not thin, f"species with <2 distinct baro_trend values: {thin}"
