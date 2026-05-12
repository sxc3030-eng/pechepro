"""Verify the worktree has the expected skeleton and pytest collects from app/."""

import importlib


def test_app_package_importable() -> None:
    mod = importlib.import_module("app")
    assert mod.__version__ == "0.1.0-dev"


def test_app_services_package_exists() -> None:
    mod = importlib.import_module("app.services")
    assert mod is not None
