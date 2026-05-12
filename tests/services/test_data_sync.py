"""Tests for app.services.data_sync — fetch curated CSVs from GitHub raw.

The canonical signature (from cross-plan amendments) is SYNC and takes a
``sqlite3.Connection``:

    def sync_curated_data(db, force=False) -> dict[str, list[str]]:

All tests below mock the network via ``respx`` and freeze time via
``freezegun`` so they are 100% deterministic.
"""

from __future__ import annotations

import datetime as dt
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


# ---------------------------------------------------------------------------
# 24h skip / 304 Not Modified / offline / 5xx
# ---------------------------------------------------------------------------


@freeze_time("2026-06-21 12:00:00")
def test_sync_skips_when_recently_synced(empty_db: sqlite3.Connection) -> None:
    """Recent sync (<24h) → skipped without HTTP call when ``force=False``."""
    # Pre-populate meta as if synced 1h ago
    empty_db.execute(
        "INSERT INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        (
            "species",
            (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat(),
            '"old"',
            0,
        ),
    )
    empty_db.commit()

    with respx.mock(
        base_url="https://raw.githubusercontent.com",
        assert_all_called=False,
    ) as router:
        species_route = router.get("/sxc3030-eng/pechepro/main/data/curated/species.csv").mock(
            return_value=httpx.Response(200, content=_SPECIES_CSV.encode("utf-8"))
        )
        # All other paths: 404
        router.route().mock(return_value=httpx.Response(404))

        result = data_sync.sync_curated_data(empty_db, force=False)

    assert "species" in result["tables_skipped"]
    # Crucially: the species route was never hit because we shortcut on age.
    assert species_route.call_count == 0


@freeze_time("2026-06-21 12:00:00")
def test_sync_handles_304_not_modified(empty_db: sqlite3.Connection) -> None:
    """Server returns 304 → table marked skipped + rows untouched + last_synced_at bumped."""
    empty_db.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    # Last sync 26h ago so we don't 24h-skip
    empty_db.execute(
        "INSERT INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        (
            "species",
            (dt.datetime.now(dt.UTC) - dt.timedelta(hours=26)).isoformat(),
            '"abc123"',
            1,
        ),
    )
    empty_db.commit()

    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.get("/sxc3030-eng/pechepro/main/data/curated/species.csv").mock(
            return_value=httpx.Response(304)
        )
        router.route().mock(return_value=httpx.Response(404))

        result = data_sync.sync_curated_data(empty_db, force=False)

    # 304 → counted as skipped (no body to upsert, but meta bumped).
    assert "species" in result["tables_skipped"]
    rows = empty_db.execute("SELECT COUNT(*) FROM species").fetchone()
    assert rows[0] == 1
    # last_synced_at advanced to the frozen "now"
    meta = empty_db.execute(
        "SELECT last_etag, row_count FROM data_sync_meta WHERE table_name = ?",
        ("species",),
    ).fetchone()
    assert meta == ('"abc123"', 1)


@freeze_time("2026-06-21 12:00:00")
def test_sync_offline_records_errors(empty_db: sqlite3.Connection) -> None:
    """All requests timeout → ``errors[]`` populated, no exception escapes."""
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.route().mock(side_effect=httpx.TimeoutException("offline"))

        result = data_sync.sync_curated_data(empty_db, force=True)

    assert result["tables_synced"] == []
    assert len(result["errors"]) == len(data_sync._SYNC_TABLES)
    # Error string mentions network or Timeout
    assert all("network" in err or "Timeout" in err for err in result["errors"])


@freeze_time("2026-06-21 12:00:00")
def test_sync_5xx_records_error_continues(empty_db: sqlite3.Connection) -> None:
    """A 503 on one table doesn't block the others."""
    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        router.get("/sxc3030-eng/pechepro/main/data/curated/species.csv").mock(
            return_value=httpx.Response(503)
        )
        router.get("/sxc3030-eng/pechepro/main/data/curated/water_types.csv").mock(
            return_value=httpx.Response(
                200,
                content=b"id,name_fr,name_en\n1,Lac,Lake\n",
                headers={"ETag": '"wt1"'},
            )
        )
        router.route().mock(return_value=httpx.Response(404))

        result = data_sync.sync_curated_data(empty_db, force=True)

    assert "water_types" in result["tables_synced"]
    # species ended up as an error (HTTP 503)
    assert any("species" in e for e in result["errors"])
    assert any("http_503" in e for e in result["errors"])


@freeze_time("2026-06-21 12:00:00")
def test_sync_force_bypasses_24h_skip(empty_db: sqlite3.Connection) -> None:
    """``force=True`` re-fetches even when the meta row is fresh."""
    empty_db.execute(
        "INSERT INTO data_sync_meta (table_name, last_synced_at, last_etag, row_count) "
        "VALUES (?, ?, ?, ?)",
        (
            "species",
            (dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)).isoformat(),
            '"old"',
            0,
        ),
    )
    empty_db.commit()

    with respx.mock(base_url="https://raw.githubusercontent.com") as router:
        species_route = router.get("/sxc3030-eng/pechepro/main/data/curated/species.csv").mock(
            return_value=httpx.Response(
                200,
                content=_SPECIES_CSV.encode("utf-8"),
                headers={"ETag": '"new"'},
            )
        )
        router.route().mock(return_value=httpx.Response(404))

        result = data_sync.sync_curated_data(empty_db, force=True)

    # Force bypassed the 24h-skip and actually hit the URL
    assert species_route.call_count == 1
    assert "species" in result["tables_synced"]
    new_meta = empty_db.execute(
        "SELECT last_etag FROM data_sync_meta WHERE table_name = ?",
        ("species",),
    ).fetchone()
    assert new_meta == ('"new"',)
