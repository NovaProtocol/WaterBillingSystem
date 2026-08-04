from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

_engine = None
_sessionmaker = None
_sync_engine = None
_sync_sessionmaker = None
_current_session: ContextVar[AsyncSession | None] = ContextVar(
    'current_session', default=None
)


def _async_url() -> str:
    """Derive the async DB URL from the configured (sync) URI by swapping the
    driver. Keeps DB_ENGINE=mysql+pymysql valid for the transitional Flask
    services while the FastAPI side uses aiomysql."""
    from config import Config

    return Config.SQLALCHEMY_DATABASE_URI.replace("+pymysql", "+aiomysql")


def init_engine() -> None:
    global _engine, _sessionmaker, _sync_engine, _sync_sessionmaker
    if _engine is not None:
        return
    from config import Config

    _engine = create_async_engine(_async_url(), pool_pre_ping=True, pool_size=5)
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    _sync_engine = create_engine(Config.SQLALCHEMY_DATABASE_URI, pool_size=5)
    _sync_sessionmaker = sessionmaker(_sync_engine, expire_on_commit=False)


async def get_db():
    """FastAPI dependency: yield a request-scoped async session and make it
    the current session for this request's context."""
    if _sessionmaker is None:
        init_engine()
    async with _sessionmaker() as session:
        token = _current_session.set(session)
        try:
            yield session
        finally:
            _current_session.reset(token)


def session() -> AsyncSession:
    """Current request-scoped async session (set by the get_db dependency)."""
    s = _current_session.get()
    if s is None:
        raise RuntimeError('No DB session bound to this context')
    return s


@asynccontextmanager
async def session_scope():
    """Open an async session and bind it as the current session (for
    lifespan/startup code that runs outside a request context)."""
    if _sessionmaker is None:
        init_engine()
    async with _sessionmaker() as s:
        token = _current_session.set(s)
        try:
            yield s
        finally:
            _current_session.reset(token)


def sync_session():
    """A fresh SYNC Session on a separate sync engine. Used to run legacy
    sync services in a threadpool (they use the Session.query API and lazy
    relationship loading, which async sessions do not support)."""
    if _sync_sessionmaker is None:
        init_engine()
    return _sync_sessionmaker()


async def init_db() -> None:
    """Create all tables (FastAPI startup). Migrations arrive with phase 2."""
    if _engine is None:
        init_engine()
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
