import sys, os
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))

import pytest
from sqlalchemy import (Boolean, Column, DateTime, Integer, MetaData, String,
                        Table, Text, create_engine)
from sqlalchemy import inspect as sa_inspect

from preflight import decide


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    md = MetaData()
    Table("users", md,
          Column("id", Integer, primary_key=True),
          Column("name", String(128)),
          Column("phone", String(64)),
          Column("active", Boolean(), nullable=False),
          Column("created_at", DateTime(), nullable=False))
    Table("orders", md,
          Column("id", Integer, primary_key=True),
          Column("user_id", Integer),
          Column("note", Text()))
    md.create_all(eng)
    return eng


@pytest.fixture()
def good_md():
    md = MetaData()
    Table("users", md,
          Column("id", Integer, primary_key=True),
          Column("name", String(128)),
          Column("phone", String(64)),
          Column("active", Boolean(), nullable=False),
          Column("created_at", DateTime(), nullable=False))
    Table("orders", md,
          Column("id", Integer, primary_key=True),
          Column("user_id", Integer),
          Column("note", Text()))
    return md


def run_decide(engine, md):
    return decide(sa_inspect(engine), md, [])


class TestTables:
    def test_healthy_no_findings(self, engine, good_md):
        assert run_decide(engine, good_md) == []

    def test_missing_table_fatal(self, engine):
        md = MetaData()
        Table("extra_table", md, Column("id", Integer, primary_key=True))
        findings = run_decide(engine, md)
        assert any(f.kind == "fatal" and "extra_table" in f.message for f in findings)


class TestColumns:
    def test_missing_column_fatal_with_ddl(self, engine, good_md):
        Table("users", good_md, Column("nickname", String(64)),
              extend_existing=True)
        findings = run_decide(engine, good_md)
        f = [f for f in findings if f.kind == "fatal" and "nickname" in f.message]
        assert f and "ALTER TABLE users ADD COLUMN nickname" in f[0].ddl

    def test_widen_varchar(self, engine):
        md = MetaData()
        Table("users", md,
              Column("id", Integer, primary_key=True),
              Column("name", String(255)),   # model bigger than DB VARCHAR(128)
              Column("phone", String(64)),
              Column("active", Boolean(), nullable=False),
              Column("created_at", DateTime(), nullable=False))
        findings = run_decide(engine, md)
        f = [f for f in findings if f.kind == "modified_column" and "name" in f.message]
        assert f and "VARCHAR(255)" in f[0].ddl

    def test_looser_db_warns(self, engine):
        md = MetaData()
        Table("users", md,
              Column("id", Integer, primary_key=True),
              Column("name", String(32)),    # model smaller than DB VARCHAR(128)
              Column("phone", String(64)),
              Column("active", Boolean(), nullable=False),
              Column("created_at", DateTime(), nullable=False))
        findings = run_decide(engine, md)
        assert any(f.kind == "warning" and "name" in f.message for f in findings)

    def test_incompatible_type_fatal(self, engine):
        md = MetaData()
        Table("users", md,
              Column("id", Integer, primary_key=True),
              Column("name", Integer()),     # model Integer vs DB VARCHAR
              Column("phone", String(64)),
              Column("active", Boolean(), nullable=False),
              Column("created_at", DateTime(), nullable=False))
        findings = run_decide(engine, md)
        assert any(f.kind == "fatal" and "name" in f.message for f in findings)

    def test_nullable_loosen_fix(self):
        eng = create_engine("sqlite:///:memory:")
        db_md = MetaData()
        Table("users", db_md,
              Column("id", Integer, primary_key=True),
              Column("name", String(128), nullable=False),  # DB is NOT NULL
              Column("phone", String(64)),
              Column("active", Boolean(), nullable=False),
              Column("created_at", DateTime(), nullable=False))
        db_md.create_all(eng)
        md = MetaData()
        Table("users", md,
              Column("id", Integer, primary_key=True),
              Column("name", String(128), nullable=True),  # model loosens it
              Column("phone", String(64)),
              Column("active", Boolean(), nullable=False),
              Column("created_at", DateTime(), nullable=False))
        findings = run_decide(eng, md)
        f = [f for f in findings if f.kind == "modified_column" and "name" in f.message]
        assert f and "loosened" in f[0].message and f[0].ddl is not None

    def test_not_null_model_warns(self, engine):
        md = MetaData()
        Table("users", md,
              Column("id", Integer, primary_key=True),
              Column("name", String(128), nullable=False),  # DB is nullable
              Column("phone", String(64)),
              Column("active", Boolean(), nullable=False),
              Column("created_at", DateTime(), nullable=False))
        findings = run_decide(engine, md)
        assert any(f.kind == "warning" and "name" in f.message for f in findings)


class TestTimeGuard:
    def test_time_named_non_datetime_fatal(self, engine, good_md):
        Table("users", good_md, Column("last_modified", String(64)),
              extend_existing=True)
        findings = run_decide(engine, good_md)
        assert any(f.kind == "fatal" and "last_modified" in f.message
                   for f in findings)

    def test_is_paid_boolean_not_fatal(self):
        eng = create_engine("sqlite:///:memory:")
        db_md = MetaData()
        Table("users", db_md,
              Column("id", Integer, primary_key=True),
              Column("is_paid", Boolean()))
        db_md.create_all(eng)
        md = MetaData()
        Table("users", md,
              Column("id", Integer, primary_key=True),
              Column("is_paid", Boolean()))
        assert run_decide(eng, md) == []
