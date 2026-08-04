from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

Base = declarative_base()

_engine = None
_sessionmaker = None


def _async_url() -> str:
    """Derive the async DB URL from the configured (sync) URI by swapping the
    driver. Keeps DB_ENGINE=mysql+pymysql valid for the transitional Flask
    services while the FastAPI side uses aiomysql."""
    from config import Config

    return Config.SQLALCHEMY_DATABASE_URI.replace("+pymysql", "+aiomysql")


def init_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
    _engine = create_async_engine(_async_url(), pool_pre_ping=True, pool_size=5)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI dependency: yield a request-scoped async session."""
    if _sessionmaker is None:
        init_engine()
    async with _sessionmaker() as session:
        yield session


async def init_db() -> None:
    """Create all tables (FastAPI startup). Migrations arrive with phase 2."""
    if _engine is None:
        init_engine()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
