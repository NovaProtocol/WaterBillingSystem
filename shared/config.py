from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, ClassVar


class Config(object):

    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parent

    SECRET_KEY: ClassVar[str] = os.environ.get("SECRET_KEY")
    NFC_PWD_SECRET: ClassVar[str] = os.environ.get("NFC_PWD_SECRET")

    SQLALCHEMY_TRACK_MODIFICATIONS: ClassVar[bool] = False

    DB_ENGINE: ClassVar[str] = os.environ.get("DB_ENGINE")
    DB_USERNAME: ClassVar[str] = os.environ.get("DB_USERNAME")
    DB_PASS: ClassVar[str] = os.environ.get("DB_PASS")
    DB_HOST: ClassVar[str] = os.environ.get("DB_HOST")
    DB_PORT: ClassVar[str] = os.environ.get("DB_PORT")
    DB_NAME: ClassVar[str] = os.environ.get("DB_NAME")

    SQLALCHEMY_DATABASE_URI: ClassVar[str] = os.environ.get(
        "SQLALCHEMY_DATABASE_URI"
    ) or "{}://{}:{}@{}:{}/{}".format(
        DB_ENGINE, DB_USERNAME, DB_PASS, DB_HOST, DB_PORT, DB_NAME
    )

    REVERSE_PROXY_PREFIX: ClassVar[str] = os.environ["REVERSE_PROXY_PREFIX"]

    REQUIRED_ENV_VARS: ClassVar[list[str]] = [
        "SECRET_KEY",
        "NFC_PWD_SECRET",
        "DB_ENGINE",
        "DB_USERNAME",
        "DB_PASS",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
    ]

    ENV_VARS_ALLOW_EMPTY: ClassVar[list[str]] = [
        "REVERSE_PROXY_PREFIX",
    ]

    @classmethod
    def validate(cls) -> None:
        missing = []
        for var in cls.REQUIRED_ENV_VARS:
            val = os.environ.get(var)
            if val is None or val.strip() == "":
                missing.append(var)
        for var in cls.ENV_VARS_ALLOW_EMPTY:
            if os.environ.get(var) is None:
                missing.append(var)
        if missing:
            print(
                "FATAL: Required environment variables are not set:\n"
                + "\n".join(f"  - {v}" for v in missing)
                + "\n\n"
                + "Create a .env file at the repository root or export them.\n"
                + "See .env.example for all required variables.",
                file=sys.stderr,
            )
            sys.exit(1)


def shared_static_dir() -> str:
    """Resolve the shared static bucket (served at /static/*).

    Order: SHARED_STATIC_DIR env -> container layout (/app/shared/static)
    -> repo layout (shared/static next to this file).
    """
    candidates = [
        os.environ["SHARED_STATIC_DIR"],
        "/app/shared/static",
        str(Path(__file__).resolve().parent / "static"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return candidates[-1]


def shared_templates_dir() -> str:
    """Resolve the shared template bucket (common base shell, etc.).

    Order: SHARED_TEMPLATES_DIR env -> container layout (/app/shared/templates)
    -> repo layout (shared/templates next to this file).
    """
    candidates = [
        os.environ["SHARED_TEMPLATES_DIR"],
        "/app/shared/templates",
        str(Path(__file__).resolve().parent / "templates"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return candidates[-1]


class ProductionConfig(Config):
    DEBUG: ClassVar[bool] = False

    # Security
    SESSION_COOKIE_HTTPONLY: ClassVar[bool] = True
    SESSION_COOKIE_SECURE: ClassVar[bool] = os.environ["SESSION_COOKIE_SECURE"].lower() in ("true", "1", "yes")
    SESSION_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    REMEMBER_COOKIE_HTTPONLY: ClassVar[bool] = True
    REMEMBER_COOKIE_SECURE: ClassVar[bool] = os.environ["SESSION_COOKIE_SECURE"].lower() in ("true", "1", "yes")
    REMEMBER_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    REMEMBER_COOKIE_DURATION: ClassVar[int] = 3600

    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict[str, Any]] = {
        "pool_size": 10,
        "pool_recycle": 3600,
        "pool_pre_ping": True,
        "pool_timeout": 5,
        "max_overflow": 2,
    }


class DebugConfig(Config):
    DEBUG: ClassVar[bool] = True


# Load all possible configurations
config_dict: dict[str, type[Config]] = {
    "Production": ProductionConfig,
    "PRODUCTION": ProductionConfig,
    "Debug": DebugConfig,
    "DEBUG": DebugConfig,
}
