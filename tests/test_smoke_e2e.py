"""End-to-end smoke: full app launch through Flask test client + GET /conditions.

Runs under the `smoke` pytest marker. Mocks pywebview AND all plan-2 services.
The goal is to verify plan-1 wiring works without any external dependency.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.init_db import apply_schema
from app.server import AppConfig, create_app
from app.services.errors import ServiceUnavailable
from app.shell import PechepoShell


@pytest.mark.smoke
def test_full_app_smoke_get_conditions(tmp_path: Path) -> None:
    """Init DB, instantiate shell (without opening window), hit /conditions."""
    db = tmp_path / "smoke.db"
    apply_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    conn.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    conn.commit()
    conn.close()

    weather = {
        "temp_air_c": 18.0,
        "pressure_hpa": 1013.0,
        "pressure_trend_6h": "rising",
        "humidity_pct": 60,
        "wind_kmh": 10,
        "cloud_cover_pct": 20,
        "fetched_at": "2026-05-09T12:00:00Z",
        "cached": False,
    }
    sun_moon = {
        "sunrise": "2026-05-09T05:30:00",
        "sunset": "2026-05-09T20:15:00",
        "civil_dawn": "2026-05-09T05:00:00",
        "civil_dusk": "2026-05-09T20:45:00",
        "moon_phase": "waxing",
        "moon_illumination": 0.42,
    }
    solunar = {
        "major": [
            {
                "start": "2026-05-09T08:00",
                "end": "2026-05-09T10:00",
                "score": 0.9,
            }
        ],
        "minor": [],
    }
    tips = [
        {
            "id": 1,
            "tip_text_fr": "Doré actif au lever du jour",
            "tip_text_en": "Walleye active at dawn",
            "source_url": "https://example.com",
            "confidence": 4,
            "match_score": 0.85,
        }
    ]

    # Instantiate the shell (initializes DB; webview patched out so no window).
    with patch("app.shell.webview"):
        PechepoShell(db_path=db, lang="fr", csv_dir=tmp_path / "no-csv-dir")

    # Now hit the Flask app via test_client.
    app = create_app(AppConfig(db_path=db, lang="fr", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=weather),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch("app.services.solunar.compute_periods", return_value=solunar),
        patch("app.services.recommender.recommend", return_value=tips),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=14.5),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=3&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            # Spec §8 acceptance: HTML contains "Doré" or "Walleye".
            assert "Doré" in body or "Walleye" in body
            # Tip rendered.
            assert "Doré actif" in body
            # Solunar period rendered.
            assert "08:00" in body
            # Water temp rendered.
            assert "14.5" in body
            # Expedia widget present.
            assert 'data-camref="1101l5IQud"' in body


@pytest.mark.smoke
def test_full_app_smoke_get_home(tmp_path: Path) -> None:
    db = tmp_path / "smoke.db"
    apply_schema(db)
    with patch("app.shell.webview"):
        PechepoShell(db_path=db, lang="en", csv_dir=tmp_path / "no-csv-dir")
    app = create_app(AppConfig(db_path=db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "pechepro" in body.lower()
        assert "Pick your fish" in body or "home.title" in body


@pytest.mark.smoke
def test_full_app_smoke_offline_weather_graceful(tmp_path: Path) -> None:
    """When Open-Meteo fails, /conditions still renders with a fallback message."""
    db = tmp_path / "smoke.db"
    apply_schema(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (3, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    conn.commit()
    conn.close()

    sun_moon = {
        "sunrise": "x",
        "sunset": "x",
        "civil_dawn": "x",
        "civil_dusk": "x",
        "moon_phase": "waxing",
        "moon_illumination": 0.5,
    }
    app = create_app(AppConfig(db_path=db, lang="en", testing=True))
    with (
        patch(
            "app.services.openmeteo_client.get_weather",
            side_effect=ServiceUnavailable(service="openmeteo", reason="DNS fail"),
        ),
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch(
            "app.services.solunar.compute_periods",
            return_value={"major": [], "minor": []},
        ),
        patch("app.services.recommender.recommend", return_value=[]),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=None),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=3&water=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True).lower()
            assert "unavailable" in body or "indisponible" in body
