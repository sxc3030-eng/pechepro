"""Tests for app.services.usgs_client — USGS Water Services water temperature.

All httpx calls are mocked with respx — no real network traffic.

Canonical signature (cross-plan amendments 2026-05-09):
    def get_water_temp(lat: float, lon: float) -> float | None
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
import respx
from freezegun import freeze_time

from app.services import usgs_client

# ----------------------------------------------------------------------------
# Fixture payloads — shaped like real USGS Water Services responses.
# https://waterservices.usgs.gov/docs/instantaneous-values/instantaneous-values-details/
# ----------------------------------------------------------------------------

# Sample USGS payload — one station, one recent temperature value (2026-06-21T12:00Z).
_USGS_OK_BODY: dict = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "TEST SITE NEAR MONTPELIER VT",
                    "siteCode": [{"value": "04287000"}],
                    "geoLocation": {
                        "geogLocation": {
                            "latitude": 44.4999,
                            "longitude": -72.0001,
                        }
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00010"}],
                    "unit": {"unitCode": "deg C"},
                },
                "values": [
                    {
                        "value": [
                            {
                                "value": "18.3",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-21T12:00:00.000-05:00",
                            }
                        ]
                    }
                ],
            }
        ]
    }
}

# Empty payload — no stations in the bbox.
_USGS_EMPTY_BODY: dict = {"value": {"timeSeries": []}}

# Payload where the most recent reading is older than 7 days.
# Using freezegun frozen date of 2026-06-21, this dateTime is > 7 days old.
_USGS_STALE_BODY: dict = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "STALE STATION",
                    "siteCode": [{"value": "04287001"}],
                    "geoLocation": {
                        "geogLocation": {
                            "latitude": 44.5,
                            "longitude": -72.0,
                        }
                    },
                },
                "variable": {
                    "variableCode": [{"value": "00010"}],
                    "unit": {"unitCode": "deg C"},
                },
                "values": [
                    {
                        "value": [
                            {
                                "value": "12.5",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-10T08:00:00.000-05:00",
                            }
                        ]
                    }
                ],
            }
        ]
    }
}

# Two stations — closer one should be picked.
_USGS_TWO_STATIONS_BODY: dict = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "FAR STATION",
                    "siteCode": [{"value": "00000001"}],
                    "geoLocation": {
                        "geogLocation": {
                            "latitude": 44.9,  # ~44km from (44.5, -72.0)
                            "longitude": -72.0,
                        }
                    },
                },
                "variable": {"variableCode": [{"value": "00010"}], "unit": {"unitCode": "deg C"}},
                "values": [
                    {
                        "value": [
                            {
                                "value": "10.0",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-21T12:00:00.000-05:00",
                            }
                        ]
                    }
                ],
            },
            {
                "sourceInfo": {
                    "siteName": "CLOSE STATION",
                    "siteCode": [{"value": "00000002"}],
                    "geoLocation": {
                        "geogLocation": {
                            "latitude": 44.51,  # ~1.1km from (44.5, -72.0)
                            "longitude": -72.0,
                        }
                    },
                },
                "variable": {"variableCode": [{"value": "00010"}], "unit": {"unitCode": "deg C"}},
                "values": [
                    {
                        "value": [
                            {
                                "value": "22.0",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-21T12:00:00.000-05:00",
                            }
                        ]
                    }
                ],
            },
        ]
    }
}

# Station farther than 50km from the requested lat/lon.
_USGS_FAR_STATION_BODY: dict = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "TOO FAR STATION",
                    "siteCode": [{"value": "99999999"}],
                    "geoLocation": {
                        "geogLocation": {
                            # ~0.6° north of requested (~66km) — outside 50km radius
                            "latitude": 45.1,
                            "longitude": -72.0,
                        }
                    },
                },
                "variable": {"variableCode": [{"value": "00010"}], "unit": {"unitCode": "deg C"}},
                "values": [
                    {
                        "value": [
                            {
                                "value": "15.0",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-21T12:00:00.000-05:00",
                            }
                        ]
                    }
                ],
            }
        ]
    }
}

# Payload with missing-value sentinel (-999999 is USGS's "no data" marker).
_USGS_MISSING_VALUE_BODY: dict = {
    "value": {
        "timeSeries": [
            {
                "sourceInfo": {
                    "siteName": "MISSING VALUE STATION",
                    "siteCode": [{"value": "11111111"}],
                    "geoLocation": {
                        "geogLocation": {
                            "latitude": 44.5,
                            "longitude": -72.0,
                        }
                    },
                },
                "variable": {"variableCode": [{"value": "00010"}], "unit": {"unitCode": "deg C"}},
                "values": [
                    {
                        "value": [
                            {
                                "value": "-999999",
                                "qualifiers": ["P"],
                                "dateTime": "2026-06-21T12:00:00.000-05:00",
                            }
                        ]
                    }
                ],
            }
        ]
    }
}


# ----------------------------------------------------------------------------
# Tests — happy path + the 5 required failure modes.
# Frozen at 2026-06-21 so the 7-day staleness window is deterministic.
# ----------------------------------------------------------------------------


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_returns_celsius_for_us_lat_lon() -> None:
    """Valid US location with nearby station returns float in Celsius."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result == pytest.approx(18.3)
    assert isinstance(result, float)


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_returns_none_for_canadian_lat_lon() -> None:
    """Outside US (Lévis QC) returns None and never hits the API."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        # Lévis QC: 46.81 lat is inside US lat range, but -71.21 lon is east of US bbox
        result = usgs_client.get_water_temp(lat=46.81, lon=-71.21)

    assert result is None
    assert route.call_count == 0


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_returns_none_for_mexican_lat_lon() -> None:
    """Outside US (Mexico City) returns None and never hits the API."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        result = usgs_client.get_water_temp(lat=19.43, lon=-99.13)

    assert result is None
    assert route.call_count == 0


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_returns_none_for_invalid_coords() -> None:
    """Out-of-bounds lat/lon returns None (no exception, no network call)."""
    assert usgs_client.get_water_temp(lat=999.0, lon=0.0) is None
    assert usgs_client.get_water_temp(lat=0.0, lon=999.0) is None
    assert usgs_client.get_water_temp(lat=-91.0, lon=-72.0) is None
    assert usgs_client.get_water_temp(lat=44.5, lon=-181.0) is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_no_station_returns_none() -> None:
    """Valid US location but USGS returns no timeSeries → None."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_EMPTY_BODY)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_no_station_within_50km_returns_none() -> None:
    """Valid US location, station exists but is >50km away → None."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_FAR_STATION_BODY)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_timeout_returns_none() -> None:
    """USGS API timeout returns None (logged, no crash)."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            side_effect=httpx.TimeoutException("timeout")
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_5xx_returns_none() -> None:
    """USGS API 5xx returns None."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(503)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_network_error_returns_none() -> None:
    """Generic network error returns None."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_malformed_json_returns_none() -> None:
    """USGS returns invalid JSON → None."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, text="<html>nope</html>")
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_stale_reading_returns_none() -> None:
    """Station exists but no temp reading in last 7 days → None."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_STALE_BODY)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_missing_value_sentinel_returns_none() -> None:
    """USGS uses -999999 to mark missing readings — must be filtered out."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_MISSING_VALUE_BODY)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert result is None


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_picks_closest_station_by_haversine() -> None:
    """When multiple stations are returned, the closest one wins."""
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_TWO_STATIONS_BODY)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    # CLOSE STATION at (44.51, -72.0) reports 22.0; FAR STATION reports 10.0.
    assert result == pytest.approx(22.0)


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_sends_parameter_cd_00010() -> None:
    """USGS expects parameterCd=00010 for water temperature (Celsius)."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    assert route.call_count == 1
    qp = dict(route.calls.last.request.url.params)
    assert qp.get("parameterCd") == "00010"
    assert qp.get("format") == "json"
    assert qp.get("siteStatus") == "active"


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_sends_bbox_around_lat_lon() -> None:
    """Bbox is computed around the requested lat/lon (~0.5°)."""
    with respx.mock() as router:
        route = router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=_USGS_OK_BODY)
        )
        usgs_client.get_water_temp(lat=44.5, lon=-72.0)

    qp = dict(route.calls.last.request.url.params)
    bbox = qp.get("bBox", "")
    parts = bbox.split(",")
    assert len(parts) == 4
    minx, miny, maxx, maxy = (float(p) for p in parts)
    assert minx < -72.0 < maxx
    assert miny < 44.5 < maxy
    # ~1° wide / 1° tall (±0.5° radius)
    assert (maxx - minx) == pytest.approx(1.0, abs=0.01)
    assert (maxy - miny) == pytest.approx(1.0, abs=0.01)


def test_get_water_temp_signature_is_sync() -> None:
    """Canonical signature: sync def, returns float | None."""
    import inspect

    assert not inspect.iscoroutinefunction(usgs_client.get_water_temp)
    sig = inspect.signature(usgs_client.get_water_temp)
    assert list(sig.parameters) == ["lat", "lon"]


def test_haversine_distance_basic() -> None:
    """Internal helper sanity check: 1° latitude ≈ 111km."""
    d_km = usgs_client._haversine_km(0.0, 0.0, 1.0, 0.0)
    assert d_km == pytest.approx(111.0, rel=0.01)


def test_us_bbox_check_includes_known_us_points() -> None:
    """Sanity: well-known US cities are inside the bbox; well-known non-US points are not."""
    # New York
    assert usgs_client._is_in_us(40.7128, -74.0060)
    # Los Angeles
    assert usgs_client._is_in_us(34.0522, -118.2437)
    # Lévis QC
    assert not usgs_client._is_in_us(46.81, -71.21)
    # Mexico City
    assert not usgs_client._is_in_us(19.43, -99.13)
    # Vancouver BC
    assert not usgs_client._is_in_us(49.28, -123.12)


@freeze_time("2026-06-21T12:30:00Z")
def test_get_water_temp_handles_datetime_at_7day_boundary() -> None:
    """Reading exactly at 7 days ago should be accepted; older should not."""
    # 6 days, 23 hours ago — should be accepted
    just_inside = (dt.datetime(2026, 6, 14, 13, 30, tzinfo=dt.UTC)).isoformat()
    body = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {
                        "siteName": "BOUNDARY",
                        "siteCode": [{"value": "0"}],
                        "geoLocation": {"geogLocation": {"latitude": 44.5, "longitude": -72.0}},
                    },
                    "variable": {
                        "variableCode": [{"value": "00010"}],
                        "unit": {"unitCode": "deg C"},
                    },
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "17.5",
                                    "qualifiers": ["P"],
                                    "dateTime": just_inside,
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    }
    with respx.mock() as router:
        router.get(url__regex=r"https://waterservices\.usgs\.gov/.*").mock(
            return_value=httpx.Response(200, json=body)
        )
        result = usgs_client.get_water_temp(lat=44.5, lon=-72.0)
    assert result == pytest.approx(17.5)
