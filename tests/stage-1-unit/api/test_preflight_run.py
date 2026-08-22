import os
import sys

BASE = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.join(BASE, "api"))
sys.path.insert(0, os.path.join(BASE, "shared"))

import preflight
import pytest
from preflight import Finding, apply
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


class TestApply:
    @pytest.mark.asyncio
    async def test_sqlite_apply_is_noop(self, tmp_path):
        db = tmp_path / "t.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE t1 (id INTEGER PRIMARY KEY, a TEXT)"))
        findings = [Finding("created_index", "x", "CREATE INDEX ix_t1_a ON t1 (a)")]
        await apply(findings, eng)
        async with eng.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='index' AND name='ix_t1_a'")
                )
            ).all()
        assert rows == []
        await eng.dispose()

    @pytest.mark.asyncio
    async def test_apply_accepts_mysql_dialect(self, tmp_path):
        # No live MySQL in unit tests; assert the dialect gate does not raise
        # for a non-mysql dialect (skips DDL with a warning log).
        db = tmp_path / "t.db"
        eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
        await apply([Finding("modified_column", "m", "ALTER TABLE t MODIFY a TEXT")], eng)
        await eng.dispose()  # must not raise


class TestRunPreflight:
    def test_fatal_manifest_exits_before_decide(self, monkeypatch):
        monkeypatch.setattr(preflight, "MANIFEST", [("ix_bad", "no_such_table", ["id"], False)])

        def fail_exit(code):
            raise SystemExit(code)

        def no_decide(*args, **kwargs):
            raise AssertionError("decide must not be reached")

        monkeypatch.setattr(preflight.sys, "exit", fail_exit)
        monkeypatch.setattr(preflight, "decide", no_decide)
        with pytest.raises(SystemExit):
            preflight.run_preflight()
