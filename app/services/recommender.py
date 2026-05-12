"""recommender — rank tips for given conditions. Plan-2 implements."""

from __future__ import annotations

import sqlite3
from typing import Any


def recommend(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int | None,
    water_type_id: int | None,
    conditions: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Rank matching tips. Plan-2 implements.

    Canonical signature locked in cross-plan amendments.
    Each result dict: {id, tip_text_fr, tip_text_en, source_url, confidence, match_score}.
    """
    raise NotImplementedError("Implemented in plan-2")
