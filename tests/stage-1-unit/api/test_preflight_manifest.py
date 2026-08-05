import sys, os
BASE = os.path.join(os.path.dirname(__file__), '..', '..', '..')
sys.path.insert(0, os.path.join(BASE, 'api'))
sys.path.insert(0, os.path.join(BASE, 'shared'))

from sqlalchemy import Column, Integer, MetaData, String, Table

from models import Base as ModelsBase
from preflight import MANIFEST, validate_manifest


class TestManifest:
    def test_manifest_matches_real_models(self):
        assert validate_manifest(ModelsBase.metadata, MANIFEST) == []

    def test_unknown_table_detected(self):
        md = MetaData()
        Table("t1", md, Column("id", Integer, primary_key=True))
        errs = validate_manifest(md, [("ix_bad", "nope", ["id"], False)])
        assert any("unknown table nope" in e for e in errs)

    def test_unknown_column_detected(self):
        md = MetaData()
        Table("t1", md, Column("id", Integer, primary_key=True))
        errs = validate_manifest(md, [("ix_bad", "t1", ["nope"], False)])
        assert any("t1 has no column nope" in e for e in errs)
