from flask_caching import Cache
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
csrf = CSRFProtect()

# Transitional wiring: models now live on the plain declarative Base in
# shared/db_async.py (framework-agnostic). Give them the Flask session's
# `.query` accessor so the existing Flask services keep working until each
# service migrates to FastAPI + async sessions.
from db_async import Base  # noqa: E402

Base.query = db.session.query_property()


def create_all() -> None:
    """Create tables for the shared declarative Base via the Flask-SQLAlchemy
    engine (transitional shim for db.create_all(), which only knows
    Flask-SQLAlchemy models). Requires an app context."""
    Base.metadata.create_all(db.engine)
