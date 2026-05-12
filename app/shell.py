"""PyWebView shell — pechepro entry point.

Orchestrates:
1. Database initialization (apply schema, recover from corruption).
2. Flask local server on a dynamic 127.0.0.1 port.
3. PyWebView native window pointing at the Flask URL.

The actual window is never opened in tests (pywebview is patched out).
"""

from __future__ import annotations

import logging
import socket
import threading
from pathlib import Path

import webview

from app.db.init_db import (
    default_db_path,
    ensure_database,
    is_db_corrupt,
    load_seed_csvs,
    recover_corrupt_db,
)
from app.i18n import detect_system_lang
from app.server import AppConfig, create_app

logger = logging.getLogger("pechepro.shell")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV_DIR = REPO_ROOT / "data" / "curated"

WINDOW_TITLE = "pechepro"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 750
WINDOW_MIN_SIZE = (900, 600)


def find_free_port() -> int:
    """Ask the OS for an available 127.0.0.1 port (bind to 0, read assigned)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def start_flask_in_thread(db_path: Path, lang: str, port: int) -> threading.Thread:
    """Start the Flask app on 127.0.0.1:port in a daemon thread."""
    cfg = AppConfig(db_path=db_path, lang=lang, testing=False)
    app = create_app(cfg)

    def _run() -> None:
        app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )

    thread = threading.Thread(target=_run, name="pechepro-flask", daemon=True)
    thread.start()
    return thread


class PechepoShell:
    """Orchestrate DB init + Flask thread + PyWebView window."""

    def __init__(self, db_path: Path, lang: str, csv_dir: Path | None = None) -> None:
        self.db_path = db_path
        self.lang = lang
        self.csv_dir = csv_dir or DEFAULT_CSV_DIR
        self._init_database()

    def _init_database(self) -> None:
        if is_db_corrupt(self.db_path):
            logger.warning("Corrupt DB detected at %s — recovering", self.db_path)
            recover_corrupt_db(self.db_path)
        is_first_run = ensure_database(self.db_path)
        if is_first_run and self.csv_dir.exists():
            counts = load_seed_csvs(self.db_path, self.csv_dir)
            logger.info("First-run seed loaded: %s", counts)

    def run(self) -> None:
        port = find_free_port()
        start_flask_in_thread(self.db_path, self.lang, port)
        url = f"http://127.0.0.1:{port}/"
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=WINDOW_MIN_SIZE,
            resizable=True,
        )
        webview.start()


def main() -> None:
    """CLI entry point — used by ``pechepro`` console script."""
    logging.basicConfig(level=logging.INFO)
    db_path = default_db_path()
    lang = detect_system_lang()
    shell = PechepoShell(db_path=db_path, lang=lang)
    shell.run()
