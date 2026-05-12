"""Shared exceptions used by service adapters and Flask error handlers."""

from __future__ import annotations


class ServiceUnavailable(Exception):
    """Raised when an external API (Open-Meteo, USGS, ECCC) is unreachable.

    The Flask handler maps this to a graceful UI message rather than HTTP 500.
    """

    def __init__(self, service: str, reason: str) -> None:
        self.service = service
        self.reason = reason
        super().__init__(f"Service '{service}' unavailable: {reason}")
