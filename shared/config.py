from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Config:
    BASE_DIR: Path = Path(__file__).resolve().parent

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "")
    NFC_PWD_SECRET: str = os.environ.get("NFC_PWD_SECRET", "")

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    DB_ENGINE: str = os.environ.get("DB_ENGINE", "")
    DB_USERNAME: str = os.environ.get("DB_USERNAME", "")
    DB_PASS: str = os.environ.get("DB_PASS", "")
    DB_HOST: str = os.environ.get("DB_HOST", "")
    DB_PORT: str = os.environ.get("DB_PORT", "")
    DB_NAME: str = os.environ.get("DB_NAME", "")

    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "SQLALCHEMY_DATABASE_URI"
    ) or "{}://{}:{}@{}:{}/{}".format(
        os.environ.get("DB_ENGINE", ""),
        os.environ.get("DB_USERNAME", ""),
        os.environ.get("DB_PASS", ""),
        os.environ.get("DB_HOST", ""),
        os.environ.get("DB_PORT", ""),
        os.environ.get("DB_NAME", ""),
    )

    REVERSE_PROXY_PREFIX: str = os.environ.get("REVERSE_PROXY_PREFIX", "")

    # Security (kept from the old ProductionConfig; hardcoded to the
    # deployment reality — HTTPS tunnel everywhere)
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SECURE: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_DURATION: int = 3600

    SQLALCHEMY_ENGINE_OPTIONS: dict = field(
        default_factory=lambda: {
            "pool_size": 10,
            "pool_recycle": 3600,
            "pool_pre_ping": True,
            "pool_timeout": 5,
            "max_overflow": 2,
        }
    )


REQUIRED_ENV_VARS = [
    "SECRET_KEY",
    "NFC_PWD_SECRET",
    "DB_ENGINE",
    "DB_USERNAME",
    "DB_PASS",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
]

ENV_VARS_ALLOW_EMPTY = [
    "REVERSE_PROXY_PREFIX",
]

_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def validate() -> None:
    missing = []
    for var in REQUIRED_ENV_VARS:
        val = os.environ.get(var)
        if val is None or val.strip() == "":
            missing.append(var)
    for var in ENV_VARS_ALLOW_EMPTY:
        if os.environ.get(var) is None:
            missing.append(var)
    if missing:
        print(
            "FATAL: Required environment variables are not set:\n"
            + "\n".join(f"  - {v}" for v in missing)
            + "\n\n"
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
        os.environ.get("SHARED_STATIC_DIR", ""),
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
        os.environ.get("SHARED_TEMPLATES_DIR", ""),
        "/app/shared/templates",
        str(Path(__file__).resolve().parent / "templates"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return candidates[-1]
