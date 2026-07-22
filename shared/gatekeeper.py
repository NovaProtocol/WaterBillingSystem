from __future__ import annotations

import logging
import os

import requests
from cachetools import TTLCache
from flask import g, redirect, request
from itsdangerous import URLSafeTimedSerializer

logger = logging.getLogger('api')

GATEKEEPER_INTERNAL = os.environ.get("GATEKEEPER_INTERNAL", "http://gatekeeper:7000")

ticket_cache = TTLCache(maxsize=128, ttl=300)
ticket_serializer = URLSafeTimedSerializer(os.environ.get("SECRET_KEY", ""), salt="ticket")


def _gatekeeper_url():
    host = request.host.split(":")[0]
    parts = host.split(".")
    if len(parts) >= 3:
        apex = ".".join(parts[-2:])
        scheme = request.scheme
        port = ""
        if ":" in request.host:
            port = ":" + request.host.split(":")[1]
        return f"{scheme}://gatekeeper.{apex}{port}"
    return f"{request.scheme}://localhost:7000"


def gatekeeper_check():
    if request.path.startswith("/static/") or request.path == "/health":
        return

    token = request.cookies.get("gatekeeper_token")
    if not token:
        return redirect(f"{_gatekeeper_url()}/?redirect={request.url}")

    cached = ticket_cache.get(token)
    if cached:
        g.ticket = cached
        return

    try:
        resp = requests.get(
            f"{GATEKEEPER_INTERNAL}/api/verify?token={token}", timeout=5
        )
        data = resp.json()
        if data.get("valid"):
            payload = ticket_serializer.loads(data["ticket"], max_age=300)
            ticket_cache[token] = payload
            g.ticket = payload
            return
    except Exception as e:
        logger.exception(f"Gatekeeper verification failed: {e}")

    return redirect(f"{_gatekeeper_url()}/?redirect={request.url}")
