"""Tests for app.services.eccc_client — ECCC water temperature (Canada).

ECCC (Environment and Climate Change Canada) publishes hydrometric/climate data
through dd.weather.gc.ca and the GeoMet REST API. Water temp coverage is sparse
(most stations report flow / discharge only); we accept partial coverage and fail
gracefully when no data exists.

Canonical signature (cross-plan amendments 2026-05-09):
    def get_water_temp(lat: float, lon: float) -> float | None

Note: tests use ``respx.mock(using='httpx')`` because the default ``httpcore``
mocker on respx 0.21.1 + httpcore 1.0.9 passes ``method`` as bytes, which breaks
``Method('GET').match`` pattern equality. The transport-level ``httpx`` mocker
sidesteps that and is the supported mocker for sync ``httpx.Client``.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.services import eccc_client

_ECCC_OK_BODY = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "STATION_NUMBER": "02OG025",
                "STATION_NAME": "TEST CA STATION",
                "WATER_TEMPERATURE": 14.6,
                "DATE": "2026-06-21T12:00:00Z",
            },
            "geometry": {"type": "Point", "coordinates": [-71.21, 46.81]},
        }
    ],
}


def test_get_water_temp_returns_celsius_for_canada() -> None:
    """Lévis QC (46.81, -71.21) with a mocked station returns the temperature."""
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)

    assert result == pytest.approx(14.6)


def test_get_water_temp_outside_canada_returns_none() -> None:
    """Vermont USA (44.5, -72.0) short-circuits before any HTTP call."""
    with respx.mock(using="httpx", assert_all_called=False) as router:
        route = router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        result = eccc_client.get_water_temp(lat=44.5, lon=-72.0)
    assert result is None
    assert route.call_count == 0


def test_get_water_temp_outside_canada_new_york_returns_none() -> None:
    """New York City (40.71, -74.01) is outside CA bounds — returns None, no call."""
    with respx.mock(using="httpx", assert_all_called=False) as router:
        route = router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        result = eccc_client.get_water_temp(lat=40.71, lon=-74.01)
    assert result is None
    assert route.call_count == 0


def test_get_water_temp_no_features_returns_none() -> None:
    """API returns empty FeatureCollection → no station nearby → returns None."""
    empty = {"type": "FeatureCollection", "features": []}
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=empty)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_features_without_temperature_returns_none() -> None:
    """Stations exist but none report WATER_TEMPERATURE — returns None gracefully."""
    body = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "STATION_NUMBER": "02OG025",
                    "STATION_NAME": "FLOW-ONLY STATION",
                    "WATER_TEMPERATURE": None,
                    "DATE": "2026-06-21T12:00:00Z",
                },
                "geometry": {"type": "Point", "coordinates": [-71.21, 46.81]},
            }
        ],
    }
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_timeout_returns_none() -> None:
    """httpx.TimeoutException is caught — returns None, never raises."""
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_5xx_returns_none() -> None:
    """API returns 500 → returns None, never raises."""
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(500)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_malformed_returns_none() -> None:
    """API returns non-JSON bytes → returns None gracefully."""
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, content=b"not json")
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_network_error_returns_none() -> None:
    """httpx.ConnectError is caught — returns None gracefully."""
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            side_effect=httpx.ConnectError("connect failed")
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_invalid_coords_returns_none() -> None:
    """Latitude 999 is impossible — returns None, never makes a call."""
    assert eccc_client.get_water_temp(lat=999.0, lon=0.0) is None


def test_get_water_temp_sends_bbox_around_lat_lon() -> None:
    """Verify bbox sent to API encloses the requested (lat, lon)."""
    with respx.mock(using="httpx") as router:
        route = router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=_ECCC_OK_BODY)
        )
        eccc_client.get_water_temp(lat=46.81, lon=-71.21)

    qp = dict(route.calls.last.request.url.params)
    bbox = qp.get("bbox", "")
    parts = bbox.split(",")
    assert len(parts) == 4
    minx, miny, maxx, maxy = (float(p) for p in parts)
    assert minx < -71.21 < maxx
    assert miny < 46.81 < maxy


def test_get_water_temp_root_not_a_dict_returns_none() -> None:
    """API returns a JSON list instead of an object → returns None."""
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=["not", "an", "object"])
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_features_not_a_list_returns_none() -> None:
    """`features` key is a string (malformed) → returns None gracefully."""
    body = {"type": "FeatureCollection", "features": "not-a-list"}
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None


def test_get_water_temp_skips_unparseable_temperature() -> None:
    """First station has garbage WATER_TEMPERATURE string, second has valid float."""
    body = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"WATER_TEMPERATURE": "not-a-number"},
                "geometry": {"type": "Point", "coordinates": [-71.21, 46.81]},
            },
            {
                "type": "Feature",
                "properties": {"WATER_TEMPERATURE": 12.3},
                "geometry": {"type": "Point", "coordinates": [-71.21, 46.81]},
            },
        ],
    }
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result == pytest.approx(12.3)


def test_get_water_temp_skips_out_of_range_temperature() -> None:
    """Station reports an absurd value (sensor stuck at 999) → skipped, returns None."""
    body = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"WATER_TEMPERATURE": 999.0},
                "geometry": {"type": "Point", "coordinates": [-71.21, 46.81]},
            },
        ],
    }
    with respx.mock(using="httpx") as router:
        router.get(url__regex=r"https://api\.weather\.gc\.ca/.*").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = eccc_client.get_water_temp(lat=46.81, lon=-71.21)
    assert result is None
