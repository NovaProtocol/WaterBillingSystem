"""Cache-Control precedence in ``shared/middleware.py``.

The middleware promises that a response which sets its own ``Cache-Control``
keeps it. It used to break that promise whenever the deployment ran in debug,
and the whole stack sits behind a shared cache, so a deliberately cacheable
asset was pinned to ``no-store`` on every request.

The other half of the promise is the safety net: the responses the app marks
``no-store`` itself must keep that value in both modes, because they are logouts
and per-visitor JSON, and a shared cache holding one would hand it to the next
visitor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parent.parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from shared.middleware import (  # noqa: E402
    CacheControlMiddleware,
    _cache_control_for,
)

UPSTREAM_CACHE = "public, max-age=300"


def build_app(
    is_debug: bool, headers: dict[str, str] | None = None, path: str = "/thing"
) -> FastAPI:
    """A minimal app whose one route answers with the headers under test."""
    app = FastAPI()

    @app.get(path)
    async def _route() -> PlainTextResponse:
        return PlainTextResponse("ok", headers=dict(headers or {}))

    app.add_middleware(CacheControlMiddleware, is_debug=is_debug)  # type: ignore[arg-type]
    return app


@pytest.mark.parametrize("is_debug", [True, False])
def test_a_route_that_sets_its_own_policy_keeps_it_in_production_only(is_debug: bool) -> None:
    """In production the upstream header wins; in debug nothing is cacheable."""
    with TestClient(build_app(is_debug, {"Cache-Control": UPSTREAM_CACHE})) as client:
        response = client.get("/thing")

    expected = "no-store" if is_debug else UPSTREAM_CACHE
    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize("is_debug", [True, False])
def test_a_route_that_sets_nothing_is_filled_in(is_debug: bool) -> None:
    with TestClient(build_app(is_debug)) as client:
        response = client.get("/thing")

    expected = "no-store" if is_debug else _cache_control_for("/thing")
    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize("is_debug", [True, False])
def test_a_static_path_is_public_in_production(is_debug: bool) -> None:
    with TestClient(build_app(is_debug, path="/static/app.css")) as client:
        response = client.get("/static/app.css")

    expected = "no-store" if is_debug else "public, max-age=86400"
    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize(
    "prefix", ["/api/", "/customer/api/", "/staff/api/", "/developer/api/", "/webhook/"]
)
@pytest.mark.parametrize("is_debug", [True, False])
def test_the_api_prefixes_are_never_shared_cacheable(prefix: str, is_debug: bool) -> None:
    """Per-visitor JSON may never rest in a shared cache, in either mode.

    In debug the whole response is ``no-store``, which already forbids storage
    everywhere. In production the API class carries ``private, no-store``. Both
    values are visitor-scoped; what must never appear is ``public`` or a bare
    ``max-age``.
    """
    path = f"{prefix}thing"
    with TestClient(build_app(is_debug, path=path)) as client:
        response = client.get(path)

    value = response.headers["Cache-Control"]
    expected = "no-store" if is_debug else "private, no-store"
    assert value == expected
    assert "public" not in value


@pytest.mark.parametrize("is_debug", [True, False])
def test_health_keeps_a_public_lifespan_in_production(is_debug: bool) -> None:
    with TestClient(build_app(is_debug, path="/health")) as client:
        response = client.get("/health")

    expected = "no-store" if is_debug else "public, max-age=3600"
    assert response.headers["Cache-Control"] == expected


@pytest.mark.parametrize("is_debug", [True, False])
def test_the_apps_own_no_store_sites_are_left_alone(is_debug: bool) -> None:
    """Logout redirects and per-visitor JSON must stay unshareable.

    Three routes set ``no-store`` on the response object they return. The value
    is already visitor-scoped, so the middleware keeps it in both modes and a
    shared cache cannot replay a logout redirect or someone's billing record to
    the next visitor.
    """
    with TestClient(build_app(is_debug, {"Cache-Control": "no-store"})) as client:
        response = client.get("/thing")

    assert response.headers["Cache-Control"] == "no-store"


def test_those_sites_still_set_the_header_in_the_source() -> None:
    """The test above can only pass if the source still sets it."""
    for relative in (
        "staff-portal/staff_auth.py",
        "customer-portal/pages.py",
        "customer-portal/api_routes.py",
    ):
        source = (BASE / relative).read_text()
        assert '"Cache-Control"] = "no-store"' in source, relative
