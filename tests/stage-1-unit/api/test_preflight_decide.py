import sys, os
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))

import pytest
from sqlalchemy import (Boolean, Column, DateTime, Integer, MetaData, Numeric,
                        String, Table, Text, create_engine)
from sqlalchemy import text as sa_text
from sqlalchemy import inspect as sa_inspect

from preflight import decide, _add_column_sql, _modify_column_sql


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


class TestModifyColumnDefault:
    def test_modify_preserves_numeric_default(self):
        col = Column("amount", Numeric(10, 2), default=0.00)
        assert "DEFAULT 0" in _modify_column_sql("bills", col)

    def test_modify_preserves_string_default(self):
        col = Column("status", String(32), default="x")
        assert "DEFAULT 'x'" in _modify_column_sql("bills", col)

    def test_modify_omits_callable_default(self):
        col = Column("amount", Numeric(10, 2), default=lambda: 1)
        assert "DEFAULT" not in _modify_column_sql("bills", col)

    def test_modify_omits_default_when_none(self):
        col = Column("amount", Numeric(10, 2))
        assert "DEFAULT" not in _modify_column_sql("bills", col)

    def test_add_still_renders_default(self):
        col = Column("amount", Numeric(10, 2), default=0.00)
        assert "DEFAULT 0" in _add_column_sql("bills", col)


class TestIndexes:
    def test_missing_model_index_created(self, engine, good_md):
        Table("users", good_md, Column("name", String(128), index=True),
              extend_existing=True)
        findings = run_decide(engine, good_md)
        f = [f for f in findings if f.kind == "created_index"]
        assert any("users" in f.message and "name" in f.message for f in f)

    def test_missing_manifest_index_created(self, engine, good_md):
        findings = decide(sa_inspect(engine), good_md,
                          [("ix_users_name_phone", "users",
                            ["name", "phone"], False)])
        f = [f for f in findings if f.kind == "created_index"]
        assert f and "ix_users_name_phone" in f[0].ddl
        assert "name, phone" in f[0].ddl

    def test_index_name_conflict_fatal(self, engine, good_md):
        # DB already has an index named ix_users_name_phone but on [id] only
        with engine.begin() as conn:
            conn.execute(sa_text("CREATE INDEX ix_users_name_phone ON users (id)"))
        findings = decide(sa_inspect(engine), good_md,
                          [("ix_users_name_phone", "users",
                            ["name", "phone"], False)])
        assert any(f.kind == "fatal" and "ix_users_name_phone" in f.message
                   for f in findings)

    def test_existing_unique_covered_by_column_set(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text(
                "ALTER TABLE users ADD COLUMN email VARCHAR(64)"))
            conn.execute(sa_text(
                "CREATE UNIQUE INDEX uq_users_email ON users (email)"))
        Table("users", good_md,
              Column("email", String(64), unique=True), extend_existing=True)
        assert run_decide(engine, good_md) == []

    def test_redundant_prefix_dropped(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text("CREATE INDEX ix_users_name ON users (name)"))
            conn.execute(sa_text(
                "CREATE INDEX ix_users_name_phone ON users (name, phone)"))
        findings = run_decide(engine, good_md)
        f = [f for f in findings if f.kind == "dropped_index"]
        assert f and "ix_users_name" in f[0].message
        assert "DROP INDEX ix_users_name" in f[0].ddl

    def test_unique_index_never_dropped(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text(
                "CREATE UNIQUE INDEX ux_users_name ON users (name)"))
            conn.execute(sa_text(
                "CREATE INDEX ix_users_name_phone ON users (name, phone)"))
        findings = run_decide(engine, good_md)
        assert not any(f.kind == "dropped_index" for f in findings)

    def test_unique_column_not_double_counted(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text(
                "ALTER TABLE users ADD COLUMN email VARCHAR(64)"))
        Table("users", good_md,
              Column("email", String(64), unique=True), extend_existing=True)
        findings = run_decide(engine, good_md)
        created = [f for f in findings if f.kind == "created_index"
                   and "email" in f.message]
        assert len(created) == 1

    def test_identical_indexes_not_dropped(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text(
                "CREATE INDEX ix_users_name_a ON users (name)"))
            conn.execute(sa_text(
                "CREATE INDEX ix_users_name_b ON users (name)"))
        findings = run_decide(engine, good_md)
        assert not any(f.kind == "dropped_index" for f in findings)

    def test_strict_prefix_drops_exactly_one(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text("CREATE INDEX ix_users_name ON users (name)"))
            conn.execute(sa_text(
                "CREATE INDEX ix_users_name_phone ON users (name, phone)"))
        findings = run_decide(engine, good_md)
        f = [f for f in findings if f.kind == "dropped_index"]
        assert len(f) == 1 and "ix_users_name" in f[0].message

    def test_covered_by_differently_named_index(self, engine, good_md):
        with engine.begin() as conn:
            conn.execute(sa_text(
                "CREATE INDEX ix_other ON users (name, phone)"))
        findings = decide(sa_inspect(engine), good_md,
                          [("ix_users_name_phone", "users",
                            ["name", "phone"], False)])
        assert not any(f.kind == "created_index" for f in findings)
        assert not any(f.kind == "fatal" for f in findings)

    def test_unique_plus_index_column_matches_sqlalchemy_ddl(self, engine, good_md):
        # SQLAlchemy materializes unique=True + index=True as a single
        # UNIQUE index named ix_<table>_<col>; preflight must expect that.
        with engine.begin() as conn:
            conn.execute(sa_text(
                "ALTER TABLE users ADD COLUMN email VARCHAR(64)"))
            conn.execute(sa_text(
                "CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        Table("users", good_md,
              Column("email", String(64), unique=True, index=True),
              extend_existing=True)
        findings = run_decide(engine, good_md)
        assert not any(f.kind == "fatal" for f in findings)
        assert not any(f.kind == "created_index" and "email" in f.message
                       for f in findings)
