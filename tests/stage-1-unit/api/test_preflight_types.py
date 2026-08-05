import sys, os
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, Integer, JSON,
                        LargeBinary, Numeric, SmallInteger, String, Text)

from preflight import TypeSpec, compare, from_db, from_model, is_time_name


class TestFromDb:
    def test_mysql_string(self):
        assert from_db("VARCHAR(64)") == TypeSpec("STRING", size=64)

    def test_mysql_text_tiers(self):
        assert from_db("TEXT").size == 1
        assert from_db("MEDIUMTEXT").size == 2
        assert from_db("LONGTEXT").size == 3

    def test_mysql_int_tiers(self):
        assert from_db("TINYINT") == TypeSpec("INTEGER", size=0)
        assert from_db("BIGINT") == TypeSpec("INTEGER", size=4)

    def test_mysql_tinyint1_is_boolean(self):
        assert from_db("TINYINT(1)") == TypeSpec("BOOLEAN")

    def test_mysql_decimal(self):
        assert from_db("DECIMAL(10, 2)") == TypeSpec("NUMERIC", precision=10, scale=2)

    def test_mysql_datetime(self):
        assert from_db("DATETIME") == TypeSpec("DATETIME")

    def test_sqlite_types(self):
        assert from_db("VARCHAR(128)") == TypeSpec("STRING", size=128)
        assert from_db("TEXT") == TypeSpec("TEXT", size=1)
        assert from_db("INTEGER") == TypeSpec("INTEGER", size=3)
        assert from_db("BOOLEAN") == TypeSpec("BOOLEAN")
        assert from_db("NUMERIC") == TypeSpec("NUMERIC", precision=None, scale=None)

    def test_unknown(self):
        assert from_db("WEIRD(9)") == TypeSpec("UNKNOWN")


class TestTypeSql:
    def test_string_default(self):
        assert TypeSpec("STRING", size=128).type_sql() == "VARCHAR(128)"

    def test_text_tiers_keep_zero(self):
        assert TypeSpec("TEXT", size=0).type_sql() == "TINYTEXT"
        assert TypeSpec("TEXT", size=1).type_sql() == "TEXT"
        assert TypeSpec("TEXT", size=2).type_sql() == "MEDIUMTEXT"
        assert TypeSpec("TEXT", size=3).type_sql() == "LONGTEXT"

    def test_int_tiers_keep_zero(self):
        assert TypeSpec("INTEGER", size=0).type_sql() == "TINYINT"
        assert TypeSpec("INTEGER", size=1).type_sql() == "SMALLINT"
        assert TypeSpec("INTEGER", size=2).type_sql() == "MEDIUMINT"
        assert TypeSpec("INTEGER", size=3).type_sql() == "INT"
        assert TypeSpec("INTEGER", size=4).type_sql() == "BIGINT"


class TestFromModel:
    def test_string(self):
        assert from_model(String(128)) == TypeSpec("STRING", size=128)

    def test_smallinteger(self):
        assert from_model(SmallInteger()) == TypeSpec("INTEGER", size=1)

    def test_biginteger(self):
        assert from_model(BigInteger()) == TypeSpec("INTEGER", size=4)

    def test_text(self):
        assert from_model(Text()) == TypeSpec("TEXT", size=1)
        assert from_model(Text(2 ** 20)) == TypeSpec("TEXT", size=2)
        assert from_model(Text(2 ** 30)) == TypeSpec("TEXT", size=3)

    def test_others(self):
        assert from_model(Integer()) == TypeSpec("INTEGER", size=3)
        assert from_model(Numeric(10, 2)) == TypeSpec("NUMERIC", precision=10, scale=2)
        assert from_model(Boolean()) == TypeSpec("BOOLEAN")
        assert from_model(DateTime()) == TypeSpec("DATETIME")
        assert from_model(Float()) == TypeSpec("FLOAT")
        assert from_model(LargeBinary()) == TypeSpec("BLOB")
        assert from_model(JSON()) == TypeSpec("JSON")


class TestCompare:
    def test_ok_identical(self):
        assert compare(TypeSpec("STRING", size=128), TypeSpec("STRING", size=128)) == "ok"

    def test_widen_string(self):
        assert compare(TypeSpec("STRING", size=64), TypeSpec("STRING", size=128)) == "widen"

    def test_warn_looser_db(self):
        assert compare(TypeSpec("STRING", size=255), TypeSpec("STRING", size=128)) == "warn"

    def test_widen_text_tier(self):
        assert compare(TypeSpec("TEXT", size=1), TypeSpec("TEXT", size=2)) == "widen"
        assert compare(TypeSpec("TEXT", size=2), TypeSpec("TEXT", size=1)) == "ok"

    def test_widen_int(self):
        assert compare(TypeSpec("INTEGER", size=0), TypeSpec("INTEGER", size=3)) == "widen"

    def test_widen_biginteger_model(self):
        assert compare(from_db("INT"), from_model(BigInteger())) == "widen"

    def test_widen_decimal(self):
        assert compare(TypeSpec("NUMERIC", precision=8, scale=2),
                       TypeSpec("NUMERIC", precision=10, scale=2)) == "widen"

    def test_decimal_missing_precision_ok(self):
        assert compare(TypeSpec("NUMERIC", precision=None, scale=None),
                       TypeSpec("NUMERIC", precision=10, scale=2)) == "ok"

    def test_fatal_family_mismatch(self):
        assert compare(TypeSpec("STRING", size=64), TypeSpec("INTEGER", size=3)) == "fatal"
        assert compare(TypeSpec("DATETIME"), TypeSpec("STRING", size=64)) == "fatal"

    def test_widthless_tinyint_is_boolean_compatible(self):
        assert compare(from_db("TINYINT"), from_model(Boolean())) == "ok"


class TestTimeName:
    def test_matches(self):
        for n in ["timestamp", "date_created", "created_at", "updated_at",
                  "scheduled_at", "started_at", "finished_at", "reversed_at",
                  "payment_timestamp", "date_paid", "last_modified"]:
            assert is_time_name(n), n

    def test_non_matches(self):
        for n in ["customer_number", "name", "is_paid", "is_active",
                  "receipt_number", "amount", "status", "id"]:
            assert not is_time_name(n), n
