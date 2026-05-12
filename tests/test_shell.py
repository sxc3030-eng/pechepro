"""Tests for app.shell — PyWebView entry point.

We never actually open a window in tests. We mock pywebview and verify
the lifecycle calls (start Flask thread, choose port, create_window, start).
"""

import socket
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.db.init_db import apply_schema
from app.shell import (
    PechepoShell,
    find_free_port,
    main,
    start_flask_in_thread,
)


def test_find_free_port_returns_int() -> None:
    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_find_free_port_returns_actually_free_port() -> None:
    port = find_free_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_start_flask_in_thread_returns_thread(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    apply_schema(db)
    port = find_free_port()
    thread = start_flask_in_thread(db_path=db, lang="en", port=port)
    assert thread.daemon
    # Thread is daemon so test exit cleans it up.


def test_pechepro_shell_init_runs_db_init(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    assert not db.exists()
    with patch("app.shell.webview") as mock_webview:
        shell = PechepoShell(db_path=db, lang="en")
        assert shell.db_path == db
        assert shell.lang == "en"
        assert db.exists()  # init_db.ensure_database created it
        assert mock_webview.create_window.call_count == 0


def test_pechepro_shell_run_calls_webview_create_and_start(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    with patch("app.shell.webview") as mock_webview:
        mock_webview.create_window = MagicMock()
        mock_webview.start = MagicMock()
        shell = PechepoShell(db_path=db, lang="en")
        shell.run()
        mock_webview.create_window.assert_called_once()
        args, kwargs = mock_webview.create_window.call_args
        assert args[0] == "pechepro"
        assert "127.0.0.1" in args[1]
        assert kwargs.get("width") == 1100
        assert kwargs.get("height") == 750
        assert kwargs.get("min_size") == (900, 600)
        mock_webview.start.assert_called_once()


def test_pechepro_shell_recovers_corrupt_db(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    db.write_bytes(b"corrupt content")
    with patch("app.shell.webview"):
        PechepoShell(db_path=db, lang="en")
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='species'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_pechepro_shell_loads_seed_on_first_run(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    # Build a csv_dir with one CSV.
    csv_dir = tmp_path / "curated"
    csv_dir.mkdir()
    (csv_dir / "species.csv").write_text(
        "id,common_name_fr,common_name_en,scientific_name,family,typical_habitat,image_url\n"
        "1,Doré,Walleye,Sander vitreus,,,\n",
        encoding="utf-8",
    )
    with patch("app.shell.webview"):
        PechepoShell(db_path=db, lang="en", csv_dir=csv_dir)
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT common_name_en FROM species").fetchall()
    conn.close()
    assert [r[0] for r in rows] == ["Walleye"]


def test_main_uses_default_db_path_and_detected_lang(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with (
        patch("app.shell.webview") as mock_webview,
        patch("app.shell.detect_system_lang", return_value="fr") as detect,
    ):
        mock_webview.create_window = MagicMock()
        mock_webview.start = MagicMock()
        main()
        detect.assert_called_once()
        mock_webview.create_window.assert_called_once()
