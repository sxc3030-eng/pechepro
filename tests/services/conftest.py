"""Service-test fixtures.

Patches a known incompatibility between respx 0.21.1 and httpx 0.28+:
httpcore passes ``request.method`` as ``bytes`` through the transport, but the
respx ``Method`` pattern compares with the ``str`` ``"GET"``. Until respx
ships a fix (>=0.22), decode bytes in ``Method.parse`` so ``router.get(...)``
mocks match real httpx requests.

Scoped to ``tests/services/`` because every plan-2 HTTP client (openmeteo,
usgs, eccc, ipapi, data_sync) goes through httpx and will hit the same bug.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from respx.patterns import Method


@pytest.fixture(autouse=True)
def _patch_respx_method_bytes() -> Iterator[None]:
    """Decode ``bytes`` method into ``str`` so respx 0.21 matches httpx 0.28 reqs."""
    original_parse = Method.parse

    def _parse(self: Method, request: object) -> str:
        method = request.method  # type: ignore[attr-defined]
        if isinstance(method, bytes | bytearray):
            return method.decode("ascii")
        return method  # type: ignore[no-any-return]

    Method.parse = _parse  # type: ignore[method-assign]
    try:
        yield
    finally:
        Method.parse = original_parse  # type: ignore[method-assign]
