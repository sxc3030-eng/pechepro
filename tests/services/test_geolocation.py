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
