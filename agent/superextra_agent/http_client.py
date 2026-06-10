"""Shared lazy httpx.AsyncClient wiring for the tool modules.

Each tool module keeps its own client (and timeout) — they share only the
create-on-first-use / close-at-exit lifecycle.
"""

import asyncio
import atexit

import httpx


class LazyAsyncClient:
    """A module's shared httpx.AsyncClient: created on first call, closed at
    interpreter exit, reset()-able in tests."""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        atexit.register(self.reset)

    def __call__(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def reset(self) -> None:
        if self._client is not None:
            try:
                asyncio.run(self._client.aclose())
            except RuntimeError:
                pass
            self._client = None
