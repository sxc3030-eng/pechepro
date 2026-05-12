"""Shared pytest fixtures."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "app" / "db" / "schema.sql"


# ---------------------------------------------------------------------------
# respx 0.21.1 ↔ httpx 0.28.1 compatibility shim
#
# respx 0.21.1 builds the proxied httpx.Request with `method=<bytes>` taken
# straight from httpcore. httpx 0.28+ preserves that as bytes (``b"GET"``)
# instead of decoding it to a string, so the Method-equality pattern in
# respx (``request.method == "GET"``) silently never matches and every
# mocked call surfaces as `AllMockedAssertionError: not mocked!`.
#
# Patching ``HTTPCoreMocker.to_httpx_request`` once at collection time fixes
# all respx-based service tests transparently.
# ---------------------------------------------------------------------------
def _install_respx_method_decode_shim() -> None:
    try:
        from respx import mocks as _respx_mocks
    except ImportError:  # pragma: no cover — respx is a dev dep, always present
        return

    mocker_cls = _respx_mocks.HTTPCoreMocker
    if getattr(mocker_cls, "_pechepro_method_shim_installed", False):
        return

    _orig_to_httpx_request = mocker_cls.to_httpx_request

    @classmethod
    def _patched_to_httpx_request(cls, **kwargs):  # type: ignore[misc]
        request = _orig_to_httpx_request.__func__(cls, **kwargs)
        if isinstance(request.method, bytes):
            # Rebuild with method decoded to str so Method patterns match.
            request = httpx.Request(
                request.method.decode("ascii"),
                request.url,
                headers=request.headers,
                stream=request.stream,
                extensions=request.extensions,
            )
        return request

    mocker_cls.to_httpx_request = _patched_to_httpx_request
    mocker_cls._pechepro_method_shim_installed = True


_install_respx_method_decode_shim()


@pytest.fixture
def empty_db(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """Provide a connection to a fresh SQLite database with schema applied."""
    db_path = tmp_path / "pechepro_test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    yield conn
    conn.close()
