"""Tests for app.services.geolocation - Windows Location API + IP fallback.

The Windows API (winsdk) is mocked across all tests so the suite runs on Linux CI too.
"""

from unittest.mock import MagicMock, patch

import httpx
import respx

from app.services import geolocation


def test_get_current_location_uses_windows_api_when_available() -> None:
    """When winsdk reports a position, return its coordinates without IP fallback."""
    fake_position = MagicMock()
    fake_position.coordinate.latitude = 46.81
    fake_position.coordinate.longitude = -71.21

    with patch.object(geolocation, "_query_windows_location", return_value=(46.81, -71.21)):
        with respx.mock(assert_all_called=False) as router:
            ipapi_route = router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(200, json={"latitude": 0.0, "longitude": 0.0})
            )
            result = geolocation.get_current_location()

    assert result == (46.81, -71.21)
    # The IP fallback must NOT be called when winsdk succeeds.
    assert ipapi_route.call_count == 0


def test_get_current_location_falls_back_to_ip() -> None:
    """If winsdk raises (e.g. permission denied), the IP fallback is used."""
    with patch.object(geolocation, "_query_windows_location", side_effect=Exception("denied")):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(
                    200, json={"latitude": 45.50, "longitude": -73.57, "city": "Montreal"}
                )
            )
            result = geolocation.get_current_location()

    assert result == (45.50, -73.57)


def test_get_current_location_returns_none_when_all_fail() -> None:
    """Both winsdk and ipapi fail (timeout) -> None."""
    with patch.object(geolocation, "_query_windows_location", side_effect=Exception("denied")):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(side_effect=httpx.TimeoutException("timeout"))
            result = geolocation.get_current_location()

    assert result is None


def test_get_current_location_ip_5xx_returns_none() -> None:
    """ipapi 503 (or any non-200) -> None, no exception propagated."""
    with patch.object(geolocation, "_query_windows_location", return_value=None):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(return_value=httpx.Response(503))
            result = geolocation.get_current_location()

    assert result is None


def test_get_current_location_ip_missing_fields_returns_none() -> None:
    """ipapi returns 200 but the payload lacks lat/lon keys -> None."""
    with patch.object(geolocation, "_query_windows_location", return_value=None):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(200, json={"city": "Levis"})
            )
            result = geolocation.get_current_location()

    assert result is None


def test_get_current_location_ip_malformed_json_returns_none() -> None:
    """ipapi 200 with non-JSON body -> None (no exception propagated)."""
    with patch.object(geolocation, "_query_windows_location", return_value=None):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(200, text="<html>rate limited</html>")
            )
            result = geolocation.get_current_location()

    assert result is None


def test_get_current_location_skips_winsdk_on_non_win32() -> None:
    """On Linux CI sys.platform != 'win32' so winsdk is skipped entirely."""
    with patch.object(geolocation.sys, "platform", "linux"):
        with respx.mock() as router:
            router.get(geolocation._IPAPI_URL).mock(
                return_value=httpx.Response(200, json={"latitude": 1.0, "longitude": 2.0})
            )
            result = geolocation.get_current_location()

    assert result == (1.0, 2.0)
