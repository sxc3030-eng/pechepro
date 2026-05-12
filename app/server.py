"""Flask local server for pechepro.

Serves Jinja2 templates and JSON APIs to the PyWebView shell. All endpoints
listen on 127.0.0.1 only — never bind 0.0.0.0.

Service call signatures follow the cross-plan amendments
(docs/superpowers/plans/2026-05-09-pechepro-cross-plan-amendments.md):

- ``astral_calc.sun_moon(lat, lon, date: datetime.date)``
- ``openmeteo_client.get_weather(lat, lon, db=g.db)``
- ``recommender.recommend(g.db, species_id, region_id, water_type_id, conditions)``

A SQLite connection is opened per request and stored on ``flask.g.db``.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, g, jsonify, render_template, request

from app.i18n import detect_system_lang, load_catalog, normalize_lang
from app.services.errors import ServiceUnavailable


@dataclass(slots=True)
class AppConfig:
    """Runtime configuration for the Flask app."""

    db_path: Path
    lang: str = "en"
    testing: bool = False


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_app(config: AppConfig | None = None) -> Flask:
    """Application factory.

    Routes are registered here. Plan-1 owns: /, /conditions, /tips,
    /api/species, /api/regions, /api/water-types, /api/sun-moon,
    /api/weather, /api/recommend, /healthz, plus 404/500/ServiceUnavailable handlers.
    """
    if config is None:
        config = AppConfig(db_path=Path("pechepro.db"), lang=detect_system_lang())

    app = Flask(__name__)
    app.config["DB_PATH"] = config.db_path
    app.config["LANG"] = normalize_lang(config.lang)
    app.config["TESTING"] = config.testing

    catalog = load_catalog(app.config["LANG"])
    app.jinja_env.globals["catalog"] = catalog
    app.jinja_env.globals["lang"] = app.config["LANG"]
    app.jinja_env.globals["t"] = lambda key: catalog.get(key, key)

    _register_db_lifecycle(app)
    _register_routes(app)
    _register_error_handlers(app)
    return app


def _register_db_lifecycle(app: Flask) -> None:
    """Open a SQLite connection on each request, close on teardown."""

    @app.before_request
    def _open_db() -> None:
        g.db = _connect(app.config["DB_PATH"])

    @app.teardown_request
    def _close_db(_exc: BaseException | None) -> None:
        db: sqlite3.Connection | None = g.pop("db", None)
        if db is not None:
            db.close()


def _season_for_date(iso_date: str) -> str:
    """Map a YYYY-MM-DD to spring/summer/fall/winter (Northern hemisphere)."""
    month = int(iso_date.split("-")[1])
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "fall"
    return "winter"


def _register_routes(app: Flask) -> None:  # noqa: C901
    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"status": "ok", "lang": app.config["LANG"]})

    @app.get("/")
    def home() -> Any:
        return render_template("home.html")

    @app.get("/api/species")
    def api_species() -> Any:
        rows = g.db.execute(
            "SELECT id, common_name_fr, common_name_en, scientific_name, "
            "family, typical_habitat, image_url FROM species ORDER BY common_name_fr"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/regions")
    def api_regions() -> Any:
        country = request.args.get("country")
        if country:
            rows = g.db.execute(
                "SELECT id, name_fr, name_en, country, iso_code, "
                "bbox_lat_min, bbox_lat_max, bbox_lon_min, bbox_lon_max "
                "FROM regions WHERE country = ? ORDER BY name_fr",
                (country,),
            ).fetchall()
        else:
            rows = g.db.execute(
                "SELECT id, name_fr, name_en, country, iso_code, "
                "bbox_lat_min, bbox_lat_max, bbox_lon_min, bbox_lon_max "
                "FROM regions ORDER BY country, name_fr"
            ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/water-types")
    def api_water_types() -> Any:
        rows = g.db.execute(
            "SELECT id, name_fr, name_en FROM water_types ORDER BY name_fr"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/sun-moon")
    def api_sun_moon() -> Any:
        from app.services import astral_calc

        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
            date_str = request.args["date"]
            date_obj = _dt.date.fromisoformat(date_str)
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid lat/lon/date"}), 400
        return jsonify(astral_calc.sun_moon(lat, lon, date_obj))

    @app.get("/api/weather")
    def api_weather() -> Any:
        from app.services import openmeteo_client

        try:
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid lat/lon"}), 400
        try:
            return jsonify(openmeteo_client.get_weather(lat, lon, db=g.db))
        except ServiceUnavailable as exc:
            return (
                jsonify(
                    {
                        "error": "weather_unavailable",
                        "service": exc.service,
                        "reason": exc.reason,
                    }
                ),
                503,
            )

    @app.post("/api/recommend")
    def api_recommend() -> Any:
        from app.services import recommender

        body = request.get_json(silent=True) or {}
        try:
            species_id = int(body["species_id"])
        except (KeyError, ValueError, TypeError):
            return jsonify({"error": "missing or invalid species_id"}), 400
        # water_type_id is optional per canonical signature (region_id | None,
        # water_type_id | None).
        water_raw = body.get("water_type_id")
        water_type_id: int | None
        if water_raw is None:
            water_type_id = None
        else:
            try:
                water_type_id = int(water_raw)
            except (ValueError, TypeError):
                return jsonify({"error": "invalid water_type_id"}), 400
        region_raw = body.get("region_id")
        region_id = int(region_raw) if region_raw is not None else None
        conditions = body.get("conditions")
        if conditions is None:
            conditions = {}
        if not isinstance(conditions, dict):
            return jsonify({"error": "conditions must be an object"}), 400
        tips = recommender.recommend(g.db, species_id, region_id, water_type_id, conditions)
        return jsonify(tips)

    @app.get("/conditions")
    def conditions_view() -> Any:
        from app.services import (
            astral_calc,
            eccc_client,
            openmeteo_client,
            recommender,
            solunar,
            usgs_client,
        )

        try:
            species_id = int(request.args["species"])
            water_type_id = int(request.args["water"])
            lat = float(request.args["lat"])
            lon = float(request.args["lon"])
        except (KeyError, ValueError):
            return jsonify({"error": "missing or invalid required params"}), 400

        region_raw = request.args.get("region")
        region_id = int(region_raw) if region_raw and region_raw.isdigit() else None
        date_str = request.args.get("date") or _dt.date.today().isoformat()
        try:
            date_obj = _dt.date.fromisoformat(date_str)
        except ValueError:
            return jsonify({"error": "invalid date"}), 400

        sp_row = g.db.execute(
            "SELECT common_name_fr, common_name_en FROM species WHERE id = ?",
            (species_id,),
        ).fetchone()
        if sp_row is None:
            return jsonify({"error": "unknown species"}), 404
        species_name = sp_row["common_name_fr" if app.config["LANG"] == "fr" else "common_name_en"]

        # Sun + moon (always succeeds — no network).
        sm = astral_calc.sun_moon(lat, lon, date_obj)
        # Solunar periods (always succeeds — no network).
        sl = solunar.compute_periods(lat, lon, date_obj)

        # Weather (graceful fallback on ServiceUnavailable).
        weather_payload: dict[str, Any] | None = None
        weather_error: str | None = None
        try:
            weather_payload = openmeteo_client.get_weather(lat, lon, db=g.db)
        except ServiceUnavailable as exc:
            weather_error = exc.reason

        # Water temp (USGS first, ECCC fallback). Both may return None.
        water_temp_c: float | None = None
        try:
            water_temp_c = usgs_client.get_water_temp(lat, lon)
        except ServiceUnavailable:
            water_temp_c = None
        if water_temp_c is None:
            try:
                water_temp_c = eccc_client.get_water_temp(lat, lon)
            except ServiceUnavailable:
                water_temp_c = None

        conditions = {
            "baro_trend": (weather_payload or {}).get("pressure_trend_6h", "any"),
            "moon_phase": sm.get("moon_phase", "any"),
            "season": _season_for_date(date_str),
            "time_of_day": "any",
            "temp_water_c": water_temp_c,
        }
        tips = recommender.recommend(g.db, species_id, region_id, water_type_id, conditions)

        return render_template(
            "conditions.html",
            species_name=species_name,
            weather=weather_payload,
            weather_error=weather_error,
            sun_moon=sm,
            solunar=sl,
            tips=tips,
            water_temp_c=water_temp_c,
        )

    @app.get("/tips")
    def tips_view() -> Any:
        species_filter = request.args.get("species")
        if species_filter and species_filter.isdigit():
            rows = g.db.execute(
                "SELECT t.id, t.tip_text_fr, t.tip_text_en, t.source_url, t.confidence, "
                "s.common_name_fr || ' / ' || s.common_name_en AS species_name "
                "FROM tips t JOIN species s ON s.id = t.species_id "
                "WHERE t.species_id = ? "
                "ORDER BY t.confidence DESC, t.id",
                (int(species_filter),),
            ).fetchall()
        else:
            rows = g.db.execute(
                "SELECT t.id, t.tip_text_fr, t.tip_text_en, t.source_url, t.confidence, "
                "s.common_name_fr || ' / ' || s.common_name_en AS species_name "
                "FROM tips t JOIN species s ON s.id = t.species_id "
                "ORDER BY t.confidence DESC, t.id"
            ).fetchall()
        tips = [dict(r) for r in rows]
        return render_template("tips.html", tips=tips)


def _register_error_handlers(app: Flask) -> None:
    def _wants_json() -> bool:
        return request.path.startswith("/api/") or request.is_json

    @app.errorhandler(404)
    def not_found(_exc: Any) -> Any:
        if _wants_json():
            return jsonify({"error": "not_found", "path": request.path}), 404
        return (
            render_template("error.html", status=404, message="Not found", detail=request.path),
            404,
        )

    @app.errorhandler(500)
    def internal_error(_exc: Any) -> Any:
        if _wants_json():
            return jsonify({"error": "internal_error"}), 500
        catalog: dict[str, str] = app.jinja_env.globals.get("catalog", {})  # type: ignore[assignment]
        return (
            render_template(
                "error.html",
                status=500,
                message="Internal error",
                detail=catalog.get("errors.backend_down", ""),
            ),
            500,
        )

    @app.errorhandler(ServiceUnavailable)
    def svc_unavailable(exc: ServiceUnavailable) -> Any:
        if _wants_json():
            return (
                jsonify(
                    {
                        "error": "service_unavailable",
                        "service": exc.service,
                        "reason": exc.reason,
                    }
                ),
                503,
            )
        return (
            render_template(
                "error.html",
                status=503,
                message="Service unavailable",
                detail=f"{exc.service}: {exc.reason}",
            ),
            503,
        )
