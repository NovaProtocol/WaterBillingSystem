from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar


class Config(object):

    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent

    # Must be set via environment variable or .env file.
    # The app will refuse to start if any of these are missing.
    SECRET_KEY: ClassVar[str] = os.getenv("SECRET_KEY")

    # NFC_PWD_SECRET — derives the PWD_AUTH password from the tag UID.
    # 256-bit hex secret. Changing it invalidates all existing tags.
    NFC_PWD_SECRET: ClassVar[str] = os.getenv("NFC_PWD_SECRET")

    SQLALCHEMY_TRACK_MODIFICATIONS: ClassVar[bool] = False

    DB_ENGINE: ClassVar[str] = os.getenv("DB_ENGINE")
    DB_USERNAME: ClassVar[str] = os.getenv("DB_USERNAME")
    DB_PASS: ClassVar[str] = os.getenv("DB_PASS")
    DB_HOST: ClassVar[str] = os.getenv("DB_HOST")
    DB_PORT: ClassVar[str] = os.getenv("DB_PORT")
    DB_NAME: ClassVar[str] = os.getenv("DB_NAME")

    SQLALCHEMY_DATABASE_URI: ClassVar[str] = "{}://{}:{}@{}:{}/{}".format(
        DB_ENGINE, DB_USERNAME, DB_PASS, DB_HOST, DB_PORT, DB_NAME
    )

    # Reverse proxy prefix (e.g. /bill-server). When set, wraps the WSGI app
    # with ProxyFix so url_for/redirects include the prefix automatically.
    # Only activate this in production behind nginx (or similar).
    REVERSE_PROXY_PREFIX: ClassVar[str] = os.getenv("REVERSE_PROXY_PREFIX", "")


class ProductionConfig(Config):
    DEBUG: ClassVar[bool] = False

    # Security
    SESSION_COOKIE_HTTPONLY: ClassVar[bool] = True
    SESSION_COOKIE_SECURE: ClassVar[bool] = True
    SESSION_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    REMEMBER_COOKIE_HTTPONLY: ClassVar[bool] = True
    REMEMBER_COOKIE_SECURE: ClassVar[bool] = True
    REMEMBER_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    REMEMBER_COOKIE_DURATION: ClassVar[int] = 3600

    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict[str, Any]] = {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
    }

    # Cache: filesystem-backed so rate limits are shared across Gunicorn workers
    CACHE_TYPE: ClassVar[str] = "FileSystemCache"
    CACHE_DIR: ClassVar[str] = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".cache"
    )


class DebugConfig(Config):
    DEBUG: ClassVar[bool] = True


# Load all possible configurations
config_dict: dict[str, type[Config]] = {
    "Production": ProductionConfig,
    "Debug": DebugConfig,
}
