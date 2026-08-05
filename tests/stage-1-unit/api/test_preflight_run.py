import sys, os
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text

from preflight import Finding, apply, decide, run_preflight


class TestApply:
    @pytest.mark.asyncio
    async def test_sqlite_apply_is_noop(self, tmp_path):
        from sqlalchemy.ext.asyncio import create_async_engine
        db = tmp_path / "t.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE t1 (id INTEGER PRIMARY KEY, a TEXT)"))
        findings = [Finding("created_index", "x",
                            "CREATE INDEX ix_t1_a ON t1 (a)")]
        await apply(findings, eng)
        async with eng.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND name='ix_t1_a'"))).all()
        assert rows == []
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_apply_accepts_mysql_dialect(self, tmp_path):
        # No live MySQL in unit tests; assert the dialect gate does not raise
        # for a non-mysql dialect (skips DDL with a warning log).
        from sqlalchemy.ext.asyncio import create_async_engine
        db = tmp_path / "t.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        await apply([Finding("modified_column", "m", "ALTER TABLE t MODIFY a TEXT")], eng)
        await eng.dispose()  # must not raise
