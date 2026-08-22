from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    """In-memory sliding-window rate limiter (per process)."""

    def __init__(self, limit: int = 10, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        recent = [t for t in self._hits[key] if now - t < self.window]
        if len(recent) >= self.limit:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)
