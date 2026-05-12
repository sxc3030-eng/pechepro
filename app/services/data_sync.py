"""Sync curated CSVs from GitHub raw into local SQLite.

Source URL pattern::

    https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated/<table>.csv

Each table is fetched at most once per 24h. Subsequent calls send the previously
recorded ``ETag`` as ``If-None-Match``; a ``304 Not Modified`` short-circuits
the upsert path. On any non-200/304 response or transport error, the table is
skipped and the failure is appended to ``result["errors"]``; the run never
raises.

Canonical signature (locked in
``docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md``)::

    def sync_curated_data(db, force=False) -> dict[str, list[str]]:

The public function is **synchronous** (Flask 3 routes are sync by default).
Internally we use ``httpx.Client``.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import sqlite3
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://raw.githubusercontent.com/sxc3030-eng/pechepro/main/data/curated"
_SYNC_INTERVAL_SECONDS = 24 * 3600
_TIMEOUT_SECONDS = 10.0

# Order matters for tables that reference foreign keys (species before tips,
# regions before tips, water_types before tips).
_SYNC_TABLES: tuple[str, ...] = (
    "species",
    "regions",
    "water_types",
    "lures",
    "color_visibility",
    "solunar_rules",
    "baro_rules",
    "tips",
)


def sync_curated_data(db: sqlite3.Connection, force: bool = False) -> dict[str, list[str]]:
    """Sync each curated table from GitHub raw into ``db``.

    For each table in :data:`_SYNC_TABLES`:

    1. Check :class:`data_sync_meta.last_synced_at` — skip if less than 24h ago
       unless ``force=True``.
    2. ``GET`` the table's CSV from GitHub raw, sending ``If-None-Match`` when
       a previous ETag is known.
    3. ``304 Not Modified`` → update ``last_synced_at`` only.
    4. ``200`` → parse the CSV (UTF-8 BOM aware), ``DELETE`` existing rows and
       ``INSERT`` the new rows in a single transaction.
    5. ``404`` / ``5xx`` / transport error → append to ``errors``; never raise.

    Returns:
        Dict with three lists: ``tables_synced``, ``tables_skipped``,
        ``errors`` (free-form strings such as ``"species: network (TimeoutException)"``).
    """
    synced: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
        for table in _SYNC_TABLES:
            try:
                if not force and _is_recently_synced(db, table):
                    skipped.append(table)
                    continue
                outcome = _sync_one_table(client, db, table)
                if outcome == "synced":
                    synced.append(table)
                elif outcome == "not_modified":
                    skipped.append(table)
                else:
                    errors.append(f"{table}: {outcome}")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                logger.warning("data_sync %s network error: %s", table, exc)
                errors.append(f"{table}: network ({type(exc).__name__})")
            except Exception as exc:
                logger.exception("data_sync %s unexpected", table)
                errors.append(f"{table}: {exc}")

    return {
        "tables_synced": synced,
        "tables_skipped": skipped,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_recently_synced(db: sqlite3.Connection, table: str) -> bool:
    row = db.execute(
        "SELECT last_synced_at FROM data_sync_meta WHERE table_name = ?",
        (table,),
    ).fetchone()
    if row is None or row[0] is None:
        return False
    last = dt.datetime.fromisoformat(row[0])
    # Be tolerant of legacy rows written without tzinfo
    if last.tzinfo is None:
        last = last.replace(tzinfo=dt.UTC)
    age = (dt.datetime.now(dt.UTC) - last).total_seconds()
    return age < _SYNC_INTERVAL_SECONDS


def _read_etag(db: sqlite3.Connection, table: str) -> str | None:
    row = db.execute(
        "SELECT last_etag FROM data_sync_meta WHERE table_name = ?",
        (table,),
    ).fetchone()
    return row[0] if row else None


def _sync_one_table(
    client: httpx.Client,
    db: sqlite3.Connection,
    table: str,
) -> str:
    """Fetch + apply one table. Returns ``synced`` / ``not_modified`` / error code."""
    url = f"{_BASE_URL}/{table}.csv"
    headers: dict[str, str] = {}
    prev_etag = _read_etag(db, table)
    if prev_etag:
        headers["If-None-Match"] = prev_etag

    response = client.get(url, headers=headers)
    status = response.status_code

    if status == 304:
        _bump_synced_at(db, table, prev_etag, None)
        return "not_modified"
    if status == 404:
        return "not_found"
    if status >= 500:
        return f"http_{status}"
    if status != 200:
        return f"http_{status}"

    # CSVs are UTF-8 with optional BOM. Decode through utf-8-sig to strip it.
    raw_bytes = response.content
    text = raw_bytes.decode("utf-8-sig")
    new_etag = response.headers.get("ETag")
    rows = list(csv.DictReader(io.StringIO(text)))
    _replace_table_rows(db, table, rows)
    _bump_synced_at(db, table, new_etag, len(rows))
    return "synced"


def _replace_table_rows(db: sqlite3.Connection, table: str, rows: list[dict[str, str]]) -> None:
    """Atomically replace all rows in ``table`` with ``rows``.

    Uses ``with db`` so the ``DELETE`` is rolled back if any ``INSERT`` fails.
    """
    # Defensive: `table` is only ever a value from _SYNC_TABLES, but assert
    # again so the f-strings below can never receive arbitrary input.
    if table not in _SYNC_TABLES:
        raise ValueError(f"refusing to mutate unknown table: {table!r}")

    if not rows:
        with db:
            db.execute(f"DELETE FROM {table}")  # noqa: S608 — table is whitelisted
        return

    columns = list(rows[0].keys())
    placeholders = ",".join("?" for _ in columns)
    column_list = ",".join(columns)
    # table comes from _SYNC_TABLES; columns come from the CSV header which is
    # under our control on GitHub. SQL injection is not in scope here.
    insert_sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"  # noqa: S608

    # Transactional refresh: if any insert fails, DELETE is rolled back too.
    with db:
        db.execute(f"DELETE FROM {table}")  # noqa: S608 — table is whitelisted
        for row in rows:
            values = [_coerce_csv_cell(row.get(c)) for c in columns]
            db.execute(insert_sql, values)


def _coerce_csv_cell(value: str | None) -> Any:
    """Empty cell → ``NULL``; everything else → raw ``str`` (SQLite coerces)."""
    if value is None or value == "":
        return None
    return value


def _bump_synced_at(
    db: sqlite3.Connection,
    table: str,
    etag: str | None,
    row_count: int | None,
) -> None:
    """Upsert the meta row, preserving ``row_count`` when the caller passes ``None``."""
    now_iso = dt.datetime.now(dt.UTC).isoformat()
    existing = db.execute(
        "SELECT row_count FROM data_sync_meta WHERE table_name = ?",
        (table,),
    ).fetchone()
    if row_count is None:
        final_count = existing[0] if existing else 0
    else:
        final_count = row_count
    with db:
        db.execute(
            "INSERT OR REPLACE INTO data_sync_meta "
            "(table_name, last_synced_at, last_etag, row_count) "
            "VALUES (?, ?, ?, ?)",
            (table, now_iso, etag, final_count),
        )
