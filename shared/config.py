from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)

    BASE_DIR: Path = Path(__file__).resolve().parent

    SECRET_KEY: str = Field(min_length=32, description="Portal JWT signing key >=32 chars")
    NFC_PWD_SECRET: str = Field(min_length=1, description="NFC password encryption secret")

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    DB_ENGINE: str = Field(min_length=1)
    DB_USERNAME: str = Field(min_length=1)
    DB_PASS: str = Field(min_length=1)
    DB_HOST: str = Field(min_length=1)
    DB_PORT: str = Field(min_length=1)
    DB_NAME: str = Field(min_length=1)

    SQLALCHEMY_DATABASE_URI: str = ""

    REVERSE_PROXY_PREFIX: str = ""

    SHARED_STATIC_DIR: str = ""
    SHARED_TEMPLATES_DIR: str = ""

    # Security (deployment reality — HTTPS tunnel everywhere)
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SECURE: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_DURATION: int = 3600

    @property
    def database_uri(self) -> str:
        if self.SQLALCHEMY_DATABASE_URI:
            return self.SQLALCHEMY_DATABASE_URI
        return "{}://{}:{}@{}:{}/{}".format(
            self.DB_ENGINE,
            self.DB_USERNAME,
            self.DB_PASS,
            self.DB_HOST,
            self.DB_PORT,
            self.DB_NAME,
        )


Config = Settings

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


@lru_cache
def get_config() -> Settings:
    return Settings()


def validate() -> None:
    try:
        get_config()
    except Exception as exc:
        print(
            "FATAL: Required environment variables are not set:\n"
            f"  - {exc}\n\n"
            + "See .env.example for all required variables.",
            file=sys.stderr,
        )
        sys.exit(1)
    return None


def shared_static_dir() -> str:
    """Resolve the shared static bucket (served at /static/*).

    Order: SHARED_STATIC_DIR env -> container layout (/app/shared/static)
    -> repo layout (shared/static next to this file).
    """
    try:
        configured = get_config().SHARED_STATIC_DIR
    except Exception:
        configured = ""
    candidates = [
        configured,
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
    try:
        configured = get_config().SHARED_TEMPLATES_DIR
    except Exception:
        configured = ""
    candidates = [
        configured,
        "/app/shared/templates",
        str(Path(__file__).resolve().parent / "templates"),
    ]
    for candidate in candidates:
        if candidate and os.path.isdir(candidate):
            return candidate
    return candidates[-1]
