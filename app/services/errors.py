"""Shared exception types for pechepro services."""


class ServiceUnavailable(Exception):
    """Raised by openmeteo / usgs / eccc when a backend is unreachable.

    The Flask error handler in app.server maps this to HTTP 503.
    """
