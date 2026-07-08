from __future__ import annotations

import os
import uuid
from datetime import datetime
from importlib import import_module
from typing import Any

from flask import Flask, Response, g, jsonify, request
from flask_caching import Cache
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
login_manager = LoginManager()
cache = Cache(config={"CACHE_TYPE": "SimpleCache"})
csrf = CSRFProtect()


def register_extensions(app: Flask) -> None:
    db.init_app(app)
    login_manager.login_view = "staff_blueprint.login"
    login_manager.init_app(app)
    cache.init_app(app)
    csrf.init_app(app)


def register_blueprints(app: Flask) -> None:
    for module_name in (
        "authentication",
        "staff",
        "landing",
        "billing",
        "api",
    ):
        module = import_module("apps.{}.routes".format(module_name))
        app.register_blueprint(module.blueprint)


def _validate_config(app_config: dict) -> None:
    missing = []
    if not app_config.get("SECRET_KEY"):
        missing.append("SECRET_KEY")
    if not app_config.get("NFC_PWD_SECRET"):
        missing.append("NFC_PWD_SECRET")
    db_uri = app_config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri or "None" in db_uri:
        missing.append("SQLALCHEMY_DATABASE_URI")
    if missing:
        raise RuntimeError(
            "Missing or invalid required configuration: {}\n"
            "Set these in your .env file or as environment variables.".format(
                ", ".join(missing)
            )
        )


def create_app(config: Any) -> Flask:

    # Contextual
    static_prefix = "/static"
    templates_dir = os.path.dirname(config.BASE_DIR)

    TEMPLATES_FOLDER = os.path.join(templates_dir, "templates")
    STATIC_FOLDER = os.path.join(templates_dir, "static")

    print(" > TEMPLATES_FOLDER: " + TEMPLATES_FOLDER)
    print(" > STATIC_FOLDER:    " + STATIC_FOLDER)

    app = Flask(
        __name__,
        static_url_path=static_prefix,
        template_folder=TEMPLATES_FOLDER,
        static_folder=STATIC_FOLDER,
    )

    app.config.from_object(config)

    _validate_config(app.config)

    register_extensions(app)
    register_blueprints(app)

    api_bp = app.blueprints.get("api_blueprint")
    if api_bp is not None:
        csrf.exempt(api_bp)

    if prefix := app.config.get("REVERSE_PROXY_PREFIX"):
        if prefix.startswith("/"):
            class PrefixMiddleware:
                def __init__(self, wsgi_app, p):
                    self.wsgi_app = wsgi_app
                    self.prefix = p.rstrip("/")
                def __call__(self, environ, start_response):
                    path = environ.get("PATH_INFO", "")
                    if path.startswith(self.prefix):
                        environ["PATH_INFO"] = path[len(self.prefix):]
                    environ["SCRIPT_NAME"] = self.prefix
                    return self.wsgi_app(environ, start_response)
            app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix)
        else:
            app.wsgi_app = ProxyFix(
                app.wsgi_app,
                x_for=1,
                x_proto=1,
                x_host=1,
                x_prefix=1,
            )

    @app.before_request
    def add_request_id() -> None:
        g.request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    @app.template_filter("timestamp_to_date")
    def timestamp_to_date(ts: int | float | datetime | None) -> str:
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        return ts.strftime("%Y-%m-%d %H:%M") if ts else ""

    @app.template_filter("datetimeformat")
    def datetimeformat(ts: int | float | datetime | None) -> str:
        if isinstance(ts, (int, float)):
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        return ts.strftime("%Y-%m-%d %H:%M") if ts else ""

    @app.errorhandler(403)
    def access_forbidden(error: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Forbidden"}), 403

    @app.errorhandler(404)
    def not_found_error(error: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def internal_error(error: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Internal server error"}), 500

    return app
