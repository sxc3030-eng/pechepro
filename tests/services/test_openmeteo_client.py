"""Tests for app.services.openmeteo_client.

Canonical signature (amendments, 2026-05-09):
    def get_weather(lat, lon, db=None) -> dict[str, Any]  # SYNC

Rules:
- All httpx calls mocked with respx (NO real network).
- Cache TTL = 1h, cache_key = "round(lat,2),round(lon,2)".
- Timeout / 5xx -> ServiceUnavailable after 2 retries.
- freezegun used for cache-TTL tests.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3

import httpx
import pytest
import respx
from freezegun import freeze_time

from app.services import openmeteo_client
from app.services.errors import ServiceUnavailable

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
_OPEN_METEO_URL_REGEX = r"https://api\.open-meteo\.com/v1/forecast.*"

_FAKE_RESPONSE = {
    "current": {
        "time": "2026-06-21T12:00",
        "temperature_2m": 22.4,
        "pressure_msl": 1015.2,
        "wind_speed_10m": 11.5,
        "relative_humidity_2m": 58,
        "cloud_cover": 35,
    },
    "hourly": {
        "time": [
            "2026-06-21T06:00",
            "2026-06-21T07:00",
            "2026-06-21T08:00",
            "2026-06-21T09:00",
            "2026-06-21T10:00",
            "2026-06-21T11:00",
        ],
        "pressure_msl": [1010.0, 1011.0, 1012.0, 1013.0, 1014.0, 1015.0],
    },
}


def _rising_response() -> dict:
    """Helper: response where pressure rises clearly across the 6h history."""
    return _FAKE_RESPONSE


def _falling_response() -> dict:
    body = json.loads(json.dumps(_FAKE_RESPONSE))
    body["hourly"]["pressure_msl"] = [1020.0, 1019.0, 1018.0, 1017.0, 1016.0, 1015.0]
    body["current"]["pressure_msl"] = 1015.0
    return body


def _steady_response() -> dict:
    body = json.loads(json.dumps(_FAKE_RESPONSE))
    body["hourly"]["pressure_msl"] = [1015.0, 1015.1, 1014.9, 1015.0, 1014.9, 1015.1]
    body["current"]["pressure_msl"] = 1015.0
    return body


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_get_weather_happy_path_no_cache() -> None:
    """Without a DB, a single Open-Meteo call returns the canonical dict."""
    with respx.mock(assert_all_called=False) as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        result = openmeteo_client.get_weather(lat=46.81, lon=-71.21, db=None)

    assert route.call_count == 1
    assert result["temp_air_c"] == pytest.approx(22.4)
    assert result["pressure_hpa"] == pytest.approx(1015.2)
    assert isinstance(result["pressure_trend_6h"], str)
    assert result["pressure_trend_6h"] in {"rising", "falling", "steady"}
    assert len(result["pressures_history_hpa"]) == 6
    assert result["pressures_history_hpa"][0] == pytest.approx(1010.0)
    assert result["wind_kmh"] == pytest.approx(11.5)
    assert result["humidity_pct"] == pytest.approx(58.0)
    assert result["cloud_cover_pct"] == pytest.approx(35.0)
    assert result["source"] == "open-meteo"
    assert result["cached"] is False
    assert "fetched_at" in result
    # fetched_at must be ISO parseable
    dt.datetime.fromisoformat(result["fetched_at"])


def test_get_weather_pressure_trend_rising() -> None:
    with respx.mock() as router:
        router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_rising_response())
        )
        result = openmeteo_client.get_weather(lat=46.81, lon=-71.21, db=None)
    assert result["pressure_trend_6h"] == "rising"


def test_get_weather_pressure_trend_falling() -> None:
    with respx.mock() as router:
        router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_falling_response())
        )
        result = openmeteo_client.get_weather(lat=46.81, lon=-71.21, db=None)
    assert result["pressure_trend_6h"] == "falling"


def test_get_weather_pressure_trend_steady() -> None:
    with respx.mock() as router:
        router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_steady_response())
        )
        result = openmeteo_client.get_weather(lat=46.81, lon=-71.21, db=None)
    assert result["pressure_trend_6h"] == "steady"


def test_get_weather_endpoint_includes_required_params() -> None:
    """The HTTP request URL must carry the Open-Meteo params from the brief."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        openmeteo_client.get_weather(lat=46.81, lon=-71.21, db=None)

    called_url = str(route.calls.last.request.url)
    # Open-Meteo params from the brief
    assert "latitude=46.81" in called_url
    assert "longitude=-71.21" in called_url
    assert "pressure_msl" in called_url
    assert "temperature_2m" in called_url
    assert "relative_humidity_2m" in called_url
    assert "wind_speed_10m" in called_url
    assert "cloud_cover" in called_url
    assert "past_hours=6" in called_url
    assert "forecast_hours=0" in called_url


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_get_weather_writes_cache_on_fresh_fetch(empty_db: sqlite3.Connection) -> None:
    """A fresh fetch with db != None must persist a weather_cache row."""
    with respx.mock() as router:
        router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    rows = empty_db.execute("SELECT cache_key, payload_json FROM weather_cache").fetchall()
    assert len(rows) == 1
    cache_key, payload_json = rows[0]
    assert cache_key == "46.81,-71.21"
    payload = json.loads(payload_json)
    assert payload["temp_air_c"] == pytest.approx(22.4)


def test_get_weather_cache_hit_within_ttl(empty_db: sqlite3.Connection) -> None:
    """Second call within TTL must NOT hit the network and must return cached=True."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        first = openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
        second = openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    assert route.call_count == 1
    assert first["cached"] is False
    assert second["cached"] is True
    # Same meteorological fields, only the cached flag differs
    for field in (
        "temp_air_c",
        "pressure_hpa",
        "pressure_trend_6h",
        "pressures_history_hpa",
        "humidity_pct",
        "wind_kmh",
        "cloud_cover_pct",
        "fetched_at",
        "source",
    ):
        assert first[field] == second[field]


def test_get_weather_cache_isolated_by_coordinates(empty_db: sqlite3.Connection) -> None:
    """Different lat/lon → different cache rows → 2 network calls."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
        openmeteo_client.get_weather(45.50, -73.57, db=empty_db)

    assert route.call_count == 2
    rows = empty_db.execute("SELECT cache_key FROM weather_cache ORDER BY cache_key").fetchall()
    assert sorted(r[0] for r in rows) == sorted(["46.81,-71.21", "45.5,-73.57"])


def test_get_weather_cache_rounds_coordinates_to_2dp(empty_db: sqlite3.Connection) -> None:
    """Users within ~1km share the same cache row (lat/lon rounded to 2dp)."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, json=_FAKE_RESPONSE)
        )
        # Both pairs round to (46.81, -71.21) — chosen to avoid banker-rounding
        # ambiguity around the .005 boundary.
        openmeteo_client.get_weather(46.8113, -71.2134, db=empty_db)
        openmeteo_client.get_weather(46.8141, -71.2089, db=empty_db)

    assert route.call_count == 1
    rows = empty_db.execute("SELECT cache_key FROM weather_cache").fetchall()
    assert {r[0] for r in rows} == {"46.81,-71.21"}


def test_get_weather_cache_expired_triggers_refetch(empty_db: sqlite3.Connection) -> None:
    """Expired entry triggers a fresh fetch."""
    initial_dt = dt.datetime(2026, 6, 21, 12, 0, 0, tzinfo=dt.UTC)
    with freeze_time(initial_dt):
        with respx.mock() as router:
            route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
                return_value=httpx.Response(200, json=_FAKE_RESPONSE)
            )
            first = openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
            assert route.call_count == 1
            assert first["cached"] is False

    # Move clock past the 1h TTL → next call must refetch
    with freeze_time(initial_dt + dt.timedelta(hours=1, minutes=1)):
        with respx.mock() as router:
            route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
                return_value=httpx.Response(200, json=_FAKE_RESPONSE)
            )
            second = openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
            assert route.call_count == 1
            assert second["cached"] is False


def test_get_weather_cache_just_under_ttl_still_hits(empty_db: sqlite3.Connection) -> None:
    """Within the 1h TTL window the cache row must still be served."""
    initial_dt = dt.datetime(2026, 6, 21, 12, 0, 0, tzinfo=dt.UTC)
    with freeze_time(initial_dt):
        with respx.mock() as router:
            router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
                return_value=httpx.Response(200, json=_FAKE_RESPONSE)
            )
            openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    with freeze_time(initial_dt + dt.timedelta(minutes=59)):
        with respx.mock(assert_all_called=False) as router:
            route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
                return_value=httpx.Response(200, json=_FAKE_RESPONSE)
            )
            cached = openmeteo_client.get_weather(46.81, -71.21, db=empty_db)
            assert route.call_count == 0
            assert cached["cached"] is True


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_get_weather_5xx_raises_service_unavailable_after_retries() -> None:
    """Persistent 503 → ServiceUnavailable raised after 2 retries (3 attempts total)."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(return_value=httpx.Response(503))
        with pytest.raises(ServiceUnavailable):
            openmeteo_client.get_weather(46.81, -71.21, db=None)

    # 1 initial + 2 retries = 3 attempts
    assert route.call_count == 3


def test_get_weather_timeout_raises_service_unavailable_after_retries() -> None:
    """Persistent timeout → ServiceUnavailable raised after 2 retries."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            side_effect=httpx.TimeoutException("boom")
        )
        with pytest.raises(ServiceUnavailable):
            openmeteo_client.get_weather(46.81, -71.21, db=None)

    assert route.call_count == 3


def test_get_weather_retries_then_succeeds() -> None:
    """First two attempts fail with 5xx, third succeeds → return weather dict."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            side_effect=[
                httpx.Response(502),
                httpx.Response(503),
                httpx.Response(200, json=_FAKE_RESPONSE),
            ]
        )
        result = openmeteo_client.get_weather(46.81, -71.21, db=None)

    assert route.call_count == 3
    assert result["temp_air_c"] == pytest.approx(22.4)
    assert result["cached"] is False


def test_get_weather_4xx_does_not_retry_and_raises_service_unavailable() -> None:
    """A 4xx (e.g. 400) is a permanent client error: no retries, ServiceUnavailable."""
    with respx.mock() as router:
        route = router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(return_value=httpx.Response(400))
        with pytest.raises(ServiceUnavailable):
            openmeteo_client.get_weather(46.81, -71.21, db=None)

    assert route.call_count == 1


def test_get_weather_malformed_json_raises_service_unavailable() -> None:
    """A malformed JSON body surfaces as ServiceUnavailable (no silent empty dict)."""
    with respx.mock() as router:
        router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(
            return_value=httpx.Response(200, content=b"not json at all")
        )
        with pytest.raises(ServiceUnavailable):
            openmeteo_client.get_weather(46.81, -71.21, db=None)


def test_get_weather_no_cache_write_on_failure(empty_db: sqlite3.Connection) -> None:
    """When backend fails, weather_cache must stay empty (no poisoned row)."""
    with respx.mock() as router:
        router.get(url__regex=_OPEN_METEO_URL_REGEX).mock(return_value=httpx.Response(503))
        with pytest.raises(ServiceUnavailable):
            openmeteo_client.get_weather(46.81, -71.21, db=empty_db)

    rows = empty_db.execute("SELECT COUNT(*) FROM weather_cache").fetchone()
    assert rows[0] == 0
