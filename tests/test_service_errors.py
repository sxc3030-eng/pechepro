"""Tests for app.services.errors module."""

import pytest

from app.services.errors import ServiceUnavailable


def test_service_unavailable_is_exception() -> None:
    assert issubclass(ServiceUnavailable, Exception)


def test_service_unavailable_carries_service_name() -> None:
    exc = ServiceUnavailable(service="openmeteo", reason="timeout")
    assert exc.service == "openmeteo"
    assert exc.reason == "timeout"
    assert "openmeteo" in str(exc)
    assert "timeout" in str(exc)


def test_service_unavailable_can_be_raised_and_caught() -> None:
    with pytest.raises(ServiceUnavailable) as exc_info:
        raise ServiceUnavailable(service="usgs", reason="404")
    assert exc_info.value.service == "usgs"
