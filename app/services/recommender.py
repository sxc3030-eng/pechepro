"""Tip recommender with hierarchical fallback.

Canonical signature locked in:
    docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md

Logic overview
--------------
1. **Hierarchical fallback** — query the `tips` table in 3 tiers and stop early
   when Tier-1 yields enough specificity. The ``water_type_id`` filter (when
   provided) is enforced as a soft constraint across **all tiers** — tips
   match if their column equals the requested value OR is NULL (NULL means
   "works in any water type"). The ``region_id`` filter is what drives the
   hierarchy:

   - **Tier 1 (exact)**: ``species_id = X AND region_id = Y`` plus the
     water_type soft filter — region-specific guidance.
   - **Tier 2 (region-agnostic)**: ``species_id = X AND region_id IS NULL``
     plus the water_type soft filter — tips marked "applicable everywhere".
   - **Tier 3 (generic species)**: ``species_id = X`` plus the water_type soft
     filter — broadest fallback when little else is available.

   If Tier-1 returns ≥3 tips, stop and return them. Otherwise add Tier-2 tips;
   if that still yields <3 tips, add Tier-3.

   When ``region_id`` is ``None`` (e.g. user opted out of regional context),
   Tier-1 is skipped and we begin at Tier-2.

2. **Scoring** — for each surviving tip:

       match_score = (matched / provided) * 0.7
                   + (confidence / 5) * 0.3
                   + tier_bonus

   where ``matched`` is the number of user-provided ``conditions`` whose value
   matches the tip's column (``'any'`` / NULL in the tip column counts as a
   soft match), ``provided`` is the number of condition keys supplied by the
   caller (defaults to 1 to avoid div-by-zero when ``conditions={}``), and
   ``tier_bonus`` is +0.2 / +0.1 / 0.0 for Tier-1 / Tier-2 / Tier-3
   respectively. Score is capped at 1.0.

3. **Ordering** — ``match_score DESC, confidence DESC, id ASC`` for stable
   deterministic ranking. The cap-at-`limit` slice is applied last.

The function takes a ``sqlite3.Connection`` as the first parameter (per the
cross-plan amendments) — the route handler in ``app.server`` injects the
``flask.g.db`` connection per request.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# Condition keys whose values are stored as TEXT columns on the `tips` row.
# Each contributes to the "matched" count of the score formula.
_TEXT_CONDITION_KEYS: tuple[str, ...] = (
    "baro_trend",
    "moon_phase",
    "season",
    "time_of_day",
)

# Maximum match_score (after tier_bonus); the spec caps the user-visible score at 1.0.
_SCORE_CAP = 1.0

# Tier_bonus values added to base score.
_TIER_BONUS: dict[int, float] = {1: 0.2, 2: 0.1, 3: 0.0}

# Threshold of Tier-1 hits below which we widen to Tier-2 / Tier-3.
_TIER1_STOP_THRESHOLD = 3

# Base SELECT — every tier returns the same row shape so the scoring loop
# can treat them uniformly.
_SELECT_COLS = (
    "SELECT id, tip_text_fr, tip_text_en, source_url, confidence, "
    "season, baro_trend, moon_phase, time_of_day, "
    "temp_water_min_c, temp_water_max_c "
    "FROM tips "
)


def recommend(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int | None,
    water_type_id: int | None,
    conditions: dict[str, Any],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return the top-N tips for the requested species/region/water-type.

    Args:
        db: open SQLite connection (schema must contain the ``tips`` table).
        species_id: mandatory species filter (TypeError if not int).
        region_id: optional region filter; ``None`` skips Tier-1 (jumps straight
            to region-agnostic tips since there's no specific region context).
        water_type_id: optional water-type filter; same semantics as region.
        conditions: dict with optional keys ``baro_trend``, ``moon_phase``,
            ``season``, ``time_of_day``, ``water_temp_c``, ``water_clarity``,
            ``light_level``. Unknown keys are silently ignored.
        limit: max number of results returned. ``limit <= 0`` → ``[]``.

    Returns:
        List of dicts with keys ``id``, ``tip_text_fr``, ``tip_text_en``,
        ``source_url``, ``confidence``, ``match_score`` (float in [0.0, 1.0]).
        Empty list when no tips match (no crash on unknown species or empty DB).

    Raises:
        TypeError: if ``species_id`` is not an integer (catches accidental
            ``None`` from a malformed request).
    """
    # ---- validation ----------------------------------------------------
    # Note: bool is a subclass of int in Python — reject it explicitly so
    # accidental True/False from a malformed request doesn't sneak past.
    if isinstance(species_id, bool) or not isinstance(species_id, int):
        raise TypeError(f"species_id must be int, got {type(species_id).__name__}")
    if limit <= 0:
        return []

    tier_rows = _collect_tier_rows(db, species_id, region_id, water_type_id)
    scored = [_score_row(tier, row, conditions) for tier, row in tier_rows]
    # Sort: match_score DESC, confidence DESC (tie-break), id ASC (stable).
    scored.sort(
        key=lambda t: (
            -t["match_score"],
            -(t["confidence"] or 0),
            t["id"],
        )
    )
    return scored[:limit]


def _collect_tier_rows(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int | None,
    water_type_id: int | None,
) -> list[tuple[int, tuple[Any, ...]]]:
    """Run the 3-tier query cascade and return rows tagged with their tier.

    Tier-1 is skipped if ``region_id`` is None. Tier-2 fires when Tier-1
    returned <3 rows; Tier-3 fires when the combined total is still <3.
    Each tier's rows are de-duplicated by ``id`` against rows already
    collected, so a tip can appear at most once (always at its highest tier).
    """
    seen_ids: set[int] = set()
    tier_rows: list[tuple[int, tuple[Any, ...]]] = []

    if region_id is not None:
        _append_unique(
            tier_rows,
            seen_ids,
            tier=1,
            rows=_query_tier1(db, species_id, region_id, water_type_id),
        )

    tier1_count = len(tier_rows)
    if tier1_count >= _TIER1_STOP_THRESHOLD:
        return tier_rows

    _append_unique(
        tier_rows,
        seen_ids,
        tier=2,
        rows=_query_tier2(db, species_id, water_type_id),
    )
    if len(tier_rows) >= _TIER1_STOP_THRESHOLD:
        return tier_rows

    _append_unique(
        tier_rows,
        seen_ids,
        tier=3,
        rows=_query_tier3(db, species_id, water_type_id),
    )
    return tier_rows


def _append_unique(
    tier_rows: list[tuple[int, tuple[Any, ...]]],
    seen_ids: set[int],
    *,
    tier: int,
    rows: list[tuple[Any, ...]],
) -> None:
    """Append ``rows`` to ``tier_rows`` tagged with ``tier``, skipping IDs
    already present in ``seen_ids`` (in-place mutation of both)."""
    for row in rows:
        if row[0] not in seen_ids:
            seen_ids.add(row[0])
            tier_rows.append((tier, row))


def _score_row(
    tier: int,
    row: tuple[Any, ...],
    user_conditions: dict[str, Any],
) -> dict[str, Any]:
    """Convert a raw SQL row + tier label into a scored result dict."""
    (rid, fr, en, src, conf, season, baro, moon, tod, tmin, tmax) = row
    score = _compute_match_score(
        tier=tier,
        tip_text_cols={
            "season": season,
            "baro_trend": baro,
            "moon_phase": moon,
            "time_of_day": tod,
        },
        tip_temp_range=(tmin, tmax),
        user_conditions=user_conditions,
        confidence=conf,
    )
    return {
        "id": rid,
        "tip_text_fr": fr,
        "tip_text_en": en,
        "source_url": src,
        "confidence": conf,
        "match_score": score,
    }


# ---------------------------------------------------------------------------
# Tier-specific SQL queries
# ---------------------------------------------------------------------------


def _query_tier1(
    db: sqlite3.Connection,
    species_id: int,
    region_id: int,
    water_type_id: int | None,
) -> list[tuple[Any, ...]]:
    """Tier 1 — exact region match. water_type filter is soft (matches own
    value OR NULL) when provided."""
    if water_type_id is not None:
        sql = (
            _SELECT_COLS
            + "WHERE species_id = ? AND region_id = ? "
            + "AND (water_type_id = ? OR water_type_id IS NULL)"
        )
        return db.execute(sql, (species_id, region_id, water_type_id)).fetchall()
    sql = _SELECT_COLS + "WHERE species_id = ? AND region_id = ?"
    return db.execute(sql, (species_id, region_id)).fetchall()


def _query_tier2(
    db: sqlite3.Connection,
    species_id: int,
    water_type_id: int | None,
) -> list[tuple[Any, ...]]:
    """Tier 2 — same species, region NULL (applicable everywhere). water_type
    filter still applies as a soft constraint when provided."""
    if water_type_id is not None:
        sql = (
            _SELECT_COLS
            + "WHERE species_id = ? AND region_id IS NULL "
            + "AND (water_type_id = ? OR water_type_id IS NULL)"
        )
        return db.execute(sql, (species_id, water_type_id)).fetchall()
    sql = _SELECT_COLS + "WHERE species_id = ? AND region_id IS NULL"
    return db.execute(sql, (species_id,)).fetchall()


def _query_tier3(
    db: sqlite3.Connection,
    species_id: int,
    water_type_id: int | None,
) -> list[tuple[Any, ...]]:
    """Tier 3 — species fallback. water_type filter still applies as a soft
    constraint when provided (NULL water_type matches anything)."""
    if water_type_id is not None:
        sql = (
            _SELECT_COLS
            + "WHERE species_id = ? "
            + "AND (water_type_id = ? OR water_type_id IS NULL)"
        )
        return db.execute(sql, (species_id, water_type_id)).fetchall()
    sql = _SELECT_COLS + "WHERE species_id = ?"
    return db.execute(sql, (species_id,)).fetchall()


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------


def _compute_match_score(
    tier: int,
    tip_text_cols: dict[str, str | None],
    tip_temp_range: tuple[float | None, float | None],
    user_conditions: dict[str, Any],
    confidence: int | None,
) -> float:
    """Combine condition match-rate, confidence, and tier bonus into a 0-1 float.

    Formula (per task instructions):
        match_score = (matched / provided) * 0.7
                    + (confidence / 5) * 0.3
                    + tier_bonus     (capped at 1.0)

    Edge cases:
      - ``conditions={}`` → ``provided`` is set to 1 to avoid div-by-zero.
        With 0 matches the ratio contribution is 0; confidence and tier_bonus
        still apply so generic tips still get a meaningful score.
      - ``confidence`` may be None (column allows it) → treat as 0.
      - User passing ``'any'`` for a condition: treat as a "wildcard" — counts
        as a soft match against any tip value.
    """
    # ---- ratio: matched / provided ------------------------------------
    matched, provided = _count_matches(
        tip_text_cols=tip_text_cols,
        tip_temp_range=tip_temp_range,
        user_conditions=user_conditions,
    )
    ratio_part = (matched / provided) * 0.7 if provided > 0 else 0.0

    # ---- confidence contribution --------------------------------------
    conf_value = float(confidence) if confidence is not None else 0.0
    confidence_part = (conf_value / 5.0) * 0.3

    # ---- tier_bonus ---------------------------------------------------
    bonus = _TIER_BONUS.get(tier, 0.0)

    score = ratio_part + confidence_part + bonus
    if score > _SCORE_CAP:
        score = _SCORE_CAP
    if score < 0.0:
        score = 0.0
    return score


def _count_matches(
    tip_text_cols: dict[str, str | None],
    tip_temp_range: tuple[float | None, float | None],
    user_conditions: dict[str, Any],
) -> tuple[int, int]:
    """Return ``(matched, provided)`` where ``provided`` is the number of
    user-supplied condition keys we evaluate (≥1 to avoid div-by-zero in caller).

    Match rules:
      - Text condition key (season / baro_trend / moon_phase / time_of_day):
        * tip column NULL or ``'any'`` → soft match (counts)
        * tip column == user value → exact match (counts)
        * user value == ``'any'`` → soft match against any tip value (counts)
        * otherwise → no match
      - ``water_temp_c``: matched if user value falls inside the tip's
        ``[temp_water_min_c, temp_water_max_c]`` range (open bounds if NULL).
        If the tip has no temp range at all (both NULL), it does not count
        toward ``provided`` — temp is a tip-side opt-in.
      - ``water_clarity`` / ``light_level``: counted in ``provided`` but
        never produce a match (V0.1 doesn't store these on tips).
    """
    matched, provided = _count_text_matches(tip_text_cols, user_conditions)
    temp_matched, temp_provided = _count_temp_match(tip_temp_range, user_conditions)
    matched += temp_matched
    provided += temp_provided
    # water_clarity / light_level: count in `provided` only if user supplied
    # them. V0.1 tips don't carry these columns; reserved for future scoring.
    for key in ("water_clarity", "light_level"):
        if user_conditions.get(key) is not None:
            provided += 1
    # Default ``provided`` to 1 to avoid div-by-zero. With 0 matches and
    # provided=1, the ratio contribution is 0 — confidence + tier_bonus
    # still drive the score for generic tips queried with no conditions.
    if provided == 0:
        provided = 1
    return matched, provided


def _count_text_matches(
    tip_text_cols: dict[str, str | None],
    user_conditions: dict[str, Any],
) -> tuple[int, int]:
    """Score the four text condition keys against the tip's text columns."""
    matched = 0
    provided = 0
    for key in _TEXT_CONDITION_KEYS:
        user_val = user_conditions.get(key)
        if user_val is None:
            continue
        provided += 1
        tip_val = tip_text_cols.get(key)
        if tip_val is None or tip_val == "any" or user_val == "any":
            matched += 1
        elif tip_val == user_val:
            matched += 1
    return matched, provided


def _count_temp_match(
    tip_temp_range: tuple[float | None, float | None],
    user_conditions: dict[str, Any],
) -> tuple[int, int]:
    """Score water_temp_c against the tip's [min, max] range (NULL = open)."""
    user_temp = user_conditions.get("water_temp_c")
    if user_temp is None:
        return 0, 0
    tmin, tmax = tip_temp_range
    if tmin is None and tmax is None:
        # Tip has no temp range — it's a wildcard, doesn't get scored.
        return 0, 0
    lo = float(tmin) if tmin is not None else float("-inf")
    hi = float(tmax) if tmax is not None else float("inf")
    try:
        within = lo <= float(user_temp) <= hi
    except (TypeError, ValueError):
        # If the user passes a non-numeric value, don't crash — treat as no match.
        return 0, 1
    return (1 if within else 0), 1
