"""Shared fixtures + compatibility shim for service tests.

httpx 0.28 changed ``httpx.Request.method`` so that a ``bytes`` value is no
longer coerced to ``str``. respx 0.21 builds the proxy ``httpx.Request`` from
httpcore's raw transport call where ``request.method`` is ``bytes`` (e.g.
``b'GET'``), then matches that against the ``Method`` pattern which stores
``'GET'`` (uppercase ``str``). The two never compare equal, so every mocked
route is silently missed and the suite raises ``AllMockedAssertionError``.

This shim wraps :meth:`respx.mocks.HTTPCoreMocker.to_httpx_request` to decode
``request.method`` if it is ``bytes`` before delegating to the original. Fix is
local to the test process — no production dependency is touched, and the patch
is idempotent (we keep a ref to the original).

Drop this file the moment respx is bumped to >= 0.22.0 (which fixed the issue
upstream).
"""

from __future__ import annotations

from typing import Any

import httpx
import respx.mocks
from respx.patterns import parse_url

_ORIGINAL_TO_HTTPX_REQUEST = respx.mocks.HTTPCoreMocker.to_httpx_request


@classmethod  # type: ignore[misc]
def _patched_to_httpx_request(cls: type, **kwargs: Any) -> httpx.Request:
    request = kwargs["request"]
    raw_url = (
        request.url.scheme,
        request.url.host,
        request.url.port,
        request.url.target,
    )
    method = request.method
    if isinstance(method, bytes):
        method = method.decode("ascii")
    return httpx.Request(
        method,
        parse_url(raw_url),
        headers=request.headers,
        stream=request.stream,
        extensions=request.extensions,
    )


# Install the shim once at import time. Pytest imports conftest before any
# test module, so respx mocks created inside service tests pick this up.
respx.mocks.HTTPCoreMocker.to_httpx_request = _patched_to_httpx_request
