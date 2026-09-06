from __future__ import annotations

import os

import httpx


def make_client(
    base_url: str | None = None,
    *,
    internal_key: str | None = None,
    container_name: str | None = None,
    staff_id: int | str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    """Shared async HTTP client for container-to-container calls.

    Mirrors the old requests-based api_client headers so the API's
    internal-key auth keeps working unchanged. When ``staff_id`` is
    supplied the caller forwards the authenticated staff identity so
    audit-sensitive routes (debug, audit-logs) don't collapse to a
    blanket internal-key bypass — the API's ``require_staff(*perms)``
    re-derives that staff and re-checks perms."""
    headers: dict[str, str] = {
        "User-Agent": "portal/1.0",
        "X-Container-Name": container_name or os.environ["CONTAINER_NAME"],
    }
    key = internal_key or os.environ.get("INTERNAL_API_KEY", "")
    if key:
        headers["X-Internal-API-Key"] = key
    if staff_id is not None:
        headers["X-Staff-ID"] = str(staff_id)
    if extra_headers:
        headers.update(extra_headers)

    return httpx.AsyncClient(
        base_url=base_url or os.environ.get("API_BASE_URL", ""),
        headers=headers,
        timeout=15.0,
    )
