"""Tests for app.services.data_sync — fetch curated CSVs from GitHub raw.

The canonical signature (from cross-plan amendments) is SYNC and takes a
``sqlite3.Connection``:

    def sync_curated_data(db, force=False) -> dict[str, list[str]]:

All tests below mock the network via ``respx`` and freeze time via
``freezegun`` so they are 100% deterministic.
"""

from __future__ import annotations

import sqlite3

import httpx
import respx
from freezegun import freeze_time

from app.services import data_sync

_SPECIES_CSV = (
    "id,common_name_fr,common_name_en,scientific_name\n"
    "3,Doré jaune,Walleye,Sander vitreus\n"
    "5,Grand brochet,Northern Pike,Esox lucius\n"
)


@freeze_time("2026-06-21 12:00:00")
def test_sync_curated_data_inserts_rows(empty_db: sqlite3.Connection) -> None:
    """Successful sync of one CSV upserts rows + records etag in data_sync_meta."""
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        # Match only the species CSV; other tables get 404 (will be skipped).
        router.get("/sxc3030-eng/pechepro/main/data/curated/species.csv").mock(
            return_value=httpx.Response(
                200,
                content=_SPECIES_CSV.encode("utf-8"),
                headers={"ETag": '"abc123"'},
            )
        )
        # All other curated tables — return 404 (treated as not_found soft error)
        router.get(url__regex=r".*\.csv").mock(return_value=httpx.Response(404))

        result = data_sync.sync_curated_data(empty_db, force=True)

    assert "species" in result["tables_synced"]
    rows = empty_db.execute("SELECT id, common_name_fr FROM species ORDER BY id").fetchall()
    assert rows == [(3, "Doré jaune"), (5, "Grand brochet")]
    meta = empty_db.execute(
        "SELECT last_etag, row_count FROM data_sync_meta WHERE table_name = ?",
        ("species",),
    ).fetchone()
    assert meta == ('"abc123"', 2)
