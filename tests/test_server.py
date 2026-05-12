"""Tests for app.server — Flask app factory + routes.

Service call signatures follow the cross-plan amendments:
- astral_calc.sun_moon(lat, lon, date: datetime.date)
- openmeteo_client.get_weather(lat, lon, db=<sqlite3.Connection>)
- recommender.recommend(db, species_id, region_id, water_type_id, conditions)
"""

import datetime as _dt
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.db.init_db import apply_schema
from app.server import AppConfig, create_app
from app.services.errors import ServiceUnavailable


@pytest.fixture
def seeded_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "p.db"
    apply_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO species (id, common_name_fr, common_name_en, scientific_name) "
        "VALUES (1, 'Doré jaune', 'Walleye', 'Sander vitreus')"
    )
    conn.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (1, 'Québec', 'Quebec', 'CA', 'QC')"
    )
    conn.execute("INSERT INTO water_types (id, name_fr, name_en) VALUES (1, 'Lac', 'Lake')")
    conn.commit()
    conn.close()
    return db_path


# ─────────── Task 9: app factory ───────────


def test_create_app_returns_flask_instance(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en"))
    assert app.name == "app.server"
    assert app.config["DB_PATH"] == seeded_db
    assert app.config["LANG"] == "en"


def test_app_config_defaults() -> None:
    cfg = AppConfig(db_path=Path("/tmp/x.db"))
    assert cfg.lang == "en"
    assert cfg.testing is False


def test_app_has_request_context_helpers(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with app.test_client() as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok", "lang": "fr"}


def test_app_injects_catalog_into_template_context(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.app_context():
        ctx = app.jinja_env.globals
        assert "catalog" in ctx
        assert "lang" in ctx
        assert ctx["lang"] == "en"
        assert ctx["catalog"]["app.title"] == "pechepro"


# ─────────── Task 10: GET / ───────────


def test_get_home_returns_html(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.content_type.startswith("text/html")
        body = resp.get_data(as_text=True)
        assert "pechepro" in body.lower()


def test_get_home_renders_in_french(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with app.test_client() as client:
        resp = client.get("/")
        body = resp.get_data(as_text=True)
        assert "Accueil" in body or "Choisissez" in body


# ─────────── Task 11: GET /api/species ───────────


def test_get_api_species_returns_seeded_rows(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/species")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        first = data[0]
        assert first["id"] == 1
        assert first["common_name_fr"] == "Doré jaune"
        assert first["common_name_en"] == "Walleye"
        assert "scientific_name" in first


def test_get_api_species_empty_db_returns_empty_list(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    apply_schema(db)
    app = create_app(AppConfig(db_path=db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/species")
        assert resp.status_code == 200
        assert resp.get_json() == []


# ─────────── Task 12: GET /api/regions ───────────


def test_get_api_regions_returns_seeded_rows(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/regions")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        first = data[0]
        assert first["id"] == 1
        assert first["country"] == "CA"
        assert first["iso_code"] == "QC"
        assert first["name_fr"] == "Québec"
        assert first["name_en"] == "Quebec"


def test_get_api_regions_filters_by_country(seeded_db: Path) -> None:
    conn = sqlite3.connect(seeded_db)
    conn.execute(
        "INSERT INTO regions (id, name_fr, name_en, country, iso_code) "
        "VALUES (50, 'New York', 'New York', 'US', 'NY')"
    )
    conn.commit()
    conn.close()
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/regions?country=US")
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["iso_code"] == "NY"


# ─────────── Task 13: GET /api/water-types ───────────


def test_get_api_water_types_returns_seeded_rows(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/water-types")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert any(d["name_en"] == "Lake" for d in data)


# ─────────── Task 14: GET /api/sun-moon (canonical: date is datetime.date) ───────────


def test_get_api_sun_moon_delegates_to_service(seeded_db: Path) -> None:
    fake_payload = {
        "sunrise": "2026-05-09T05:30:00-04:00",
        "sunset": "2026-05-09T20:15:00-04:00",
        "civil_dawn": "2026-05-09T05:00:00-04:00",
        "civil_dusk": "2026-05-09T20:45:00-04:00",
        "moon_phase": "waxing",
        "moon_illumination": 0.42,
    }
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.astral_calc.sun_moon", return_value=fake_payload) as m:
        with app.test_client() as client:
            resp = client.get("/api/sun-moon?lat=46.81&lon=-71.21&date=2026-05-09")
            assert resp.status_code == 200
            assert resp.get_json() == fake_payload
            m.assert_called_once_with(46.81, -71.21, _dt.date(2026, 5, 9))


def test_get_api_sun_moon_missing_params_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/sun-moon")
        assert resp.status_code == 400
        assert "error" in resp.get_json()


def test_get_api_sun_moon_invalid_lat_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/sun-moon?lat=abc&lon=-71.21&date=2026-05-09")
        assert resp.status_code == 400


def test_get_api_sun_moon_invalid_date_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/sun-moon?lat=46.81&lon=-71.21&date=not-a-date")
        assert resp.status_code == 400


# ─────────── Task 15: GET /api/weather (canonical: db=g.db kwarg) ───────────


def test_get_api_weather_returns_payload(seeded_db: Path) -> None:
    fake = {
        "temp_air_c": 18.5,
        "pressure_hpa": 1013.2,
        "pressure_trend_6h": "rising",
        "humidity_pct": 64,
        "wind_kmh": 12.0,
        "cloud_cover_pct": 30,
        "fetched_at": "2026-05-09T12:00:00Z",
        "cached": False,
    }
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.openmeteo_client.get_weather", return_value=fake) as m:
        with app.test_client() as client:
            resp = client.get("/api/weather?lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            assert resp.get_json() == fake
            args, kwargs = m.call_args
            assert args == (46.81, -71.21)
            assert "db" in kwargs
            assert isinstance(kwargs["db"], sqlite3.Connection)


def test_get_api_weather_returns_503_on_service_unavailable(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    err = ServiceUnavailable(service="openmeteo", reason="timeout")
    with patch("app.services.openmeteo_client.get_weather", side_effect=err):
        with app.test_client() as client:
            resp = client.get("/api/weather?lat=46.81&lon=-71.21")
            assert resp.status_code == 503
            body = resp.get_json()
            assert body["error"] == "weather_unavailable"
            assert "openmeteo" in body["service"]


def test_get_api_weather_missing_params_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/weather")
        assert resp.status_code == 400


# ─────────── Task 16: POST /api/recommend (canonical: db=g.db first arg) ───────────


def test_post_api_recommend_returns_ranked_tips(seeded_db: Path) -> None:
    fake = [
        {
            "id": 1,
            "tip_text_fr": "FR1",
            "tip_text_en": "EN1",
            "source_url": "u1",
            "confidence": 4,
            "match_score": 0.9,
        },
        {
            "id": 2,
            "tip_text_fr": "FR2",
            "tip_text_en": "EN2",
            "source_url": "u2",
            "confidence": 3,
            "match_score": 0.6,
        },
    ]
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.recommender.recommend", return_value=fake) as m:
        with app.test_client() as client:
            payload = {
                "species_id": 1,
                "region_id": 1,
                "water_type_id": 1,
                "conditions": {
                    "baro_trend": "rising",
                    "moon_phase": "waxing",
                    "season": "spring",
                    "time_of_day": "dawn",
                    "temp_water_c": 12.5,
                },
            }
            resp = client.post("/api/recommend", json=payload)
            assert resp.status_code == 200
            assert resp.get_json() == fake
            args, _kwargs = m.call_args
            # canonical: (db, species_id, region_id, water_type_id, conditions)
            assert isinstance(args[0], sqlite3.Connection)
            assert args[1:] == (1, 1, 1, payload["conditions"])


def test_post_api_recommend_missing_body_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.post("/api/recommend", json={})
        assert resp.status_code == 400


def test_post_api_recommend_handles_null_region(seeded_db: Path) -> None:
    fake = [
        {
            "id": 1,
            "tip_text_fr": "x",
            "tip_text_en": "x",
            "source_url": None,
            "confidence": 3,
            "match_score": 0.5,
        }
    ]
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with patch("app.services.recommender.recommend", return_value=fake) as m:
        with app.test_client() as client:
            resp = client.post(
                "/api/recommend",
                json={
                    "species_id": 1,
                    "region_id": None,
                    "water_type_id": 1,
                    "conditions": {},
                },
            )
            assert resp.status_code == 200
            args, _kwargs = m.call_args
            assert isinstance(args[0], sqlite3.Connection)
            assert args[1:] == (1, None, 1, {})


# ─────────── Task 17: GET /conditions (full orchestration) ───────────


def _common_service_payloads() -> dict[str, Any]:
    return {
        "weather": {
            "temp_air_c": 18.0,
            "pressure_hpa": 1013.0,
            "pressure_trend_6h": "rising",
            "humidity_pct": 60,
            "wind_kmh": 10,
            "cloud_cover_pct": 20,
            "fetched_at": "2026-05-09T12:00:00Z",
            "cached": False,
        },
        "sun_moon": {
            "sunrise": "2026-05-09T05:30:00",
            "sunset": "2026-05-09T20:15:00",
            "civil_dawn": "2026-05-09T05:00:00",
            "civil_dusk": "2026-05-09T20:45:00",
            "moon_phase": "waxing",
            "moon_illumination": 0.42,
        },
        "solunar": {
            "major": [
                {
                    "start": "2026-05-09T08:00:00",
                    "end": "2026-05-09T10:00:00",
                    "score": 0.9,
                }
            ],
            "minor": [
                {
                    "start": "2026-05-09T14:00:00",
                    "end": "2026-05-09T15:00:00",
                    "score": 0.6,
                }
            ],
        },
        "tips": [
            {
                "id": 1,
                "tip_text_fr": "FR1",
                "tip_text_en": "EN1",
                "source_url": "u1",
                "confidence": 4,
                "match_score": 0.9,
            }
        ],
    }


def test_get_conditions_orchestrates_all_services(seeded_db: Path) -> None:
    p = _common_service_payloads()
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=p["weather"]),
        patch("app.services.astral_calc.sun_moon", return_value=p["sun_moon"]),
        patch("app.services.solunar.compute_periods", return_value=p["solunar"]),
        patch("app.services.recommender.recommend", return_value=p["tips"]),
        patch("app.services.usgs_client.get_water_temp", return_value=14.0),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            assert "EN1" in body
            assert "Walleye" in body


def test_get_conditions_renders_in_french(seeded_db: Path) -> None:
    p = _common_service_payloads()
    p["tips"] = [
        {
            "id": 1,
            "tip_text_fr": "Astuce FR",
            "tip_text_en": "Tip EN",
            "source_url": None,
            "confidence": 4,
            "match_score": 0.9,
        }
    ]
    app = create_app(AppConfig(db_path=seeded_db, lang="fr", testing=True))
    with (
        patch("app.services.openmeteo_client.get_weather", return_value=p["weather"]),
        patch("app.services.astral_calc.sun_moon", return_value=p["sun_moon"]),
        patch("app.services.solunar.compute_periods", return_value=p["solunar"]),
        patch("app.services.recommender.recommend", return_value=p["tips"]),
        patch("app.services.usgs_client.get_water_temp", return_value=None),
        patch("app.services.eccc_client.get_water_temp", return_value=14.5),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21")
            body = resp.get_data(as_text=True)
            assert "Astuce FR" in body
            assert "Doré jaune" in body


def test_get_conditions_handles_weather_unavailable_gracefully(seeded_db: Path) -> None:
    sun_moon = {
        "sunrise": "x",
        "sunset": "x",
        "civil_dawn": "x",
        "civil_dusk": "x",
        "moon_phase": "waxing",
        "moon_illumination": 0.5,
    }
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with (
        patch(
            "app.services.openmeteo_client.get_weather",
            side_effect=ServiceUnavailable(service="openmeteo", reason="timeout"),
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
            resp = client.get("/conditions?species=1&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 200
            body = resp.get_data(as_text=True)
            assert "unavailable" in body.lower() or "indisponible" in body.lower()


def test_get_conditions_missing_required_params_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/conditions")
        assert resp.status_code == 400


def test_get_conditions_unknown_species_returns_404(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    sun_moon = {
        "sunrise": "x",
        "sunset": "x",
        "civil_dawn": "x",
        "civil_dusk": "x",
        "moon_phase": "waxing",
        "moon_illumination": 0.5,
    }
    with (
        patch("app.services.astral_calc.sun_moon", return_value=sun_moon),
        patch(
            "app.services.solunar.compute_periods",
            return_value={"major": [], "minor": []},
        ),
    ):
        with app.test_client() as client:
            resp = client.get("/conditions?species=999&water=1&region=1&lat=46.81&lon=-71.21")
            assert resp.status_code == 404


def test_get_conditions_invalid_date_returns_400(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/conditions?species=1&water=1&lat=46.81&lon=-71.21&date=nope")
        assert resp.status_code == 400


# ─────────── Task 18: GET /tips ───────────


def _seed_one_tip(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO tips (species_id, water_type_id, tip_text_fr, tip_text_en, "
        "source_url, confidence) VALUES (1, 1, 'Astuce A', 'Tip A', 'https://x', 4)"
    )
    conn.commit()
    conn.close()


def test_get_tips_renders_all_tips(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/tips")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Tip A" in body


def test_get_tips_filters_by_species(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/tips?species=1")
        assert resp.status_code == 200
        assert "Tip A" in resp.get_data(as_text=True)


def test_get_tips_unknown_species_returns_empty(seeded_db: Path) -> None:
    _seed_one_tip(seeded_db)
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/tips?species=999")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Tip A" not in body


# ─────────── Task 19: error handlers ───────────


def test_404_returns_json_for_api_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/api/does-not-exist")
        assert resp.status_code == 404
        assert resp.content_type.startswith("application/json")
        body = resp.get_json()
        assert body["error"] == "not_found"


def test_404_returns_html_for_page_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))
    with app.test_client() as client:
        resp = client.get("/missing-page")
        assert resp.status_code == 404
        assert resp.content_type.startswith("text/html")


def test_500_returns_json_for_api_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))

    @app.get("/api/boom")
    def boom() -> Any:
        raise RuntimeError("explode")

    app.config["TESTING"] = False
    with app.test_client() as client:
        resp = client.get("/api/boom")
        assert resp.status_code == 500
        assert resp.get_json()["error"] == "internal_error"


def test_service_unavailable_handler_for_html_pages(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))

    @app.get("/dies")
    def dies() -> Any:
        raise ServiceUnavailable(service="x", reason="y")

    app.config["TESTING"] = False
    with app.test_client() as client:
        resp = client.get("/dies")
        assert resp.status_code == 503
        body = resp.get_data(as_text=True)
        assert "unavailable" in body.lower()


def test_service_unavailable_handler_for_api_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))

    @app.get("/api/dies")
    def dies() -> Any:
        raise ServiceUnavailable(service="usgs", reason="dns")

    app.config["TESTING"] = False
    with app.test_client() as client:
        resp = client.get("/api/dies")
        assert resp.status_code == 503
        body = resp.get_json()
        assert body["error"] == "service_unavailable"
        assert body["service"] == "usgs"


def test_500_returns_html_for_page_routes(seeded_db: Path) -> None:
    app = create_app(AppConfig(db_path=seeded_db, lang="en", testing=True))

    @app.get("/page-boom")
    def boom() -> Any:
        raise RuntimeError("explode")

    app.config["TESTING"] = False
    with app.test_client() as client:
        resp = client.get("/page-boom")
        assert resp.status_code == 500
        assert resp.content_type.startswith("text/html")
