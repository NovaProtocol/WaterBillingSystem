from __future__ import annotations

import os

import httpx


def make_client(
    base_url: str | None = None,
    *,
    internal_key: str | None = None,
    container_name: str | None = None,
) -> httpx.AsyncClient:
    """Shared async HTTP client for container-to-container calls.

    Mirrors the old requests-based api_client headers so the API's
    internal-key auth keeps working unchanged."""
    headers = {
        "User-Agent": "portal/1.0",
        "X-Container-Name": container_name or os.environ["CONTAINER_NAME"],
    }
    key = internal_key or os.environ["INTERNAL_API_KEY"]
    if key:
        headers["X-Internal-API-Key"] = key

    return httpx.AsyncClient(
        base_url=base_url or os.environ["API_BASE_URL"],
        headers=headers,
        timeout=15.0,
    )
