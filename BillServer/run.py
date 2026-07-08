from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask.cli import with_appcontext

dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path)
from flask_migrate import Migrate
from flask_migrate.cli import db as db_group
from sqlalchemy import inspect as sa_inspect

from apps import create_app, db
from apps.config import config_dict

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

_debug_worker_proc: subprocess.Popen | None = None

parser = argparse.ArgumentParser(description="BillServer")
parser.add_argument(
    "--deployment_type",
    choices=["DEBUG", "PRODUCTION"],
    default=os.environ.get("DEPLOYMENT_TYPE"),
    help="Run mode ($DEPLOYMENT_TYPE env var, required)",
)
parser.add_argument("--ssl-cert", default=None, help="Path to SSL certificate (PEM)")
parser.add_argument("--ssl-key", default=None, help="Path to SSL private key (PEM)")
args, _ = parser.parse_known_args()

if not args.deployment_type:
    print(
        "FATAL: DEPLOYMENT_TYPE is not set. Must be DEBUG or PRODUCTION.\n"
        "Set it in your .env file or as an environment variable.",
        file=sys.stderr,
    )
    sys.exit(1)

DEBUG = args.deployment_type == "DEBUG"

get_config_mode = "Debug" if DEBUG else "Production"

try:
    app_config = config_dict[get_config_mode.capitalize()]
except KeyError:
    exit("Error: Invalid <config_mode>. Expected values [Debug, Production] ")

app_config.validate()

app = create_app(app_config)

Migrate(app, db)

with app.app_context():
    logger.info("=== PREFLIGHT (module) ===")
    logger.info("Checking if database tables exist...")
    try:
        db.create_all()
    except Exception as e:
        logger.error("FATAL: db.create_all() failed: %s", e)
        sys.exit(1)
    for table_name in sorted(db.metadata.tables.keys()):
        logger.info("  [OK] table: %s", table_name)
    logger.info("=== PREFLIGHT (module) DONE ===")


# Custom CLI commands attached to `flask db` group
@db_group.command("wipe")
@with_appcontext
def wipe() -> None:
    """Delete all data from all tables but keep schema."""
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.commit()
    logger.info("All data cleared. Tables preserved.")


if DEBUG:
    app.logger.info("DEBUG            = " + str(DEBUG))
    app.logger.info("Page Compression = " + "FALSE" if DEBUG else "TRUE")
    app.logger.info("DBMS             = " + app_config.SQLALCHEMY_DATABASE_URI)

def _compile_scss(app: Flask) -> None:
    import os

    import sass

    scss_dir = os.path.join(app.static_folder, "assets", "scss")
    css_dir = os.path.join(app.static_folder, "assets", "css")
    os.makedirs(css_dir, exist_ok=True)

    for fname in os.listdir(scss_dir):
        if not fname.endswith(".scss"):
            continue
        scss_path = os.path.join(scss_dir, fname)
        css_name = fname.replace(".scss", ".css")
        css_path = os.path.join(css_dir, css_name)
        try:
            with open(scss_path) as f:
                scss_content = f.read()
            css = sass.compile(string=scss_content, output_style="compressed")
            with open(css_path, "w") as f:
                f.write(css)
            logger.info("Compiled %s", css_name)
        except Exception as e:
            logger.warning("Failed to compile %s: %s", fname, e)


def _preflight_db(app: Flask) -> None:
    """Run pre-flight DB checks and superuser seeding. Called at startup."""
    from apps.authentication.util import hash_pass
    from apps.models import Staff

    with app.app_context():
        logger.info("Checking database connectivity...")
        try:
            db.session.execute(db.text("SELECT 1"))
            db.session.commit()
        except Exception as e:
            logger.error("FATAL: Cannot connect to database: %s", e)
            logger.error("Ensure the MySQL container is running and accessible.")
            sys.exit(1)

        logger.info("Database connection OK")

        logger.info("=== Checking individual tables ===")
        db.create_all()
        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        expected_tables = set(db.metadata.tables.keys())
        for table_name in sorted(expected_tables):
            status = "[EXISTS]" if table_name in existing_tables else "[CREATED]"
            logger.info("  %s table: %s", status, table_name)

        missing_tables = expected_tables - existing_tables
        if missing_tables:
            logger.warning("Tables still missing after create_all: %s", ", ".join(sorted(missing_tables)))
        else:
            logger.info("All %d tables present", len(expected_tables))

        superuser = Staff.query.filter_by(username="superuser").first()
        if not superuser:
            superuser = Staff(
                username="superuser",
                name="Superuser",
                password=hash_pass("superuser"),
                can_read_meters=True,
                can_accept_payment=True,
                can_enroll_customer=True,
                can_drop_reading=True,
                can_drop_payment=True,
                can_enroll_staff=True,
                can_manage_billing=True,
            )
            db.session.add(superuser)
            db.session.commit()
            logger.info(
                "Created superuser account (username: superuser, password: superuser)"
            )
        else:
            logger.info("Superuser account verified")

        for table_name in sorted(expected_tables):
            existing_columns = {
                col["name"] for col in inspector.get_columns(table_name)
            }
            expected_columns = {
                col.name for col in db.metadata.tables[table_name].columns
            }
            missing_cols = expected_columns - existing_columns
            if missing_cols:
                logger.warning(
                    'Table "%s" missing columns (run flask db upgrade): %s',
                    table_name,
                    ", ".join(sorted(missing_cols)),
                )

        logger.info("All table columns verified")


def _start_debug_worker() -> subprocess.Popen | None:
    global _debug_worker_proc
    worker_script = Path(__file__).resolve().parent / "apps" / "staff" / "debug_worker.py"
    if not worker_script.exists():
        logger.warning("Debug worker script not found: %s", worker_script)
        return None
    proc = subprocess.Popen(
        [sys.executable, str(worker_script)],
        start_new_session=True,
    )
    _debug_worker_proc = proc
    logger.info("Debug worker started (PID %d)", proc.pid)
    return proc


def _stop_debug_worker() -> None:
    global _debug_worker_proc
    if _debug_worker_proc is None:
        return
    try:
        pgid = os.getpgid(_debug_worker_proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        _debug_worker_proc.wait(timeout=5)
    except Exception:
        try:
            _debug_worker_proc.kill()
            _debug_worker_proc.wait(timeout=3)
        except Exception:
            pass
    _debug_worker_proc = None


if __name__ == "__main__":
    _compile_scss(app)
    _preflight_db(app)
    _start_debug_worker()

    try:
        if DEBUG:
            ssl_cert = args.ssl_cert
            ssl_key = args.ssl_key
            if ssl_cert is None and Path("certificates/dev-cert.pem").exists():
                ssl_cert = "certificates/dev-cert.pem"
            if ssl_key is None and Path("certificates/dev-key.pem").exists():
                ssl_key = "certificates/dev-key.pem"
            if ssl_cert and ssl_key:
                logger.info("HTTPS enabled (cert: %s)", ssl_cert)
                app.run(host="0.0.0.0", port=5005, debug=DEBUG, ssl_context=(ssl_cert, ssl_key))
            else:
                app.run(host="0.0.0.0", port=5005, debug=DEBUG)
        else:
            try:
                from gunicorn.app.base import BaseApplication
            except ImportError:
                logger.error("gunicorn is not installed. Run: pip install gunicorn")
                sys.exit(1)

            class StandaloneApplication(BaseApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()

                def load_config(self):
                    for key, value in self.options.items():
                        self.cfg.set(key, value)

                def load(self):
                    return self.application

            gunicorn_opts = {
                "bind": "0.0.0.0:5005",
                "workers": 3,
                "accesslog": "-",
                "loglevel": "info",
                "capture_output": True,
                "enable_stdio_inheritance": True,
            }
            ssl_certfile = os.environ.get("SSL_CERTFILE")
            ssl_keyfile = os.environ.get("SSL_KEYFILE")
            if ssl_certfile:
                gunicorn_opts["certfile"] = ssl_certfile
                if ssl_keyfile:
                    gunicorn_opts["keyfile"] = ssl_keyfile
                logger.info("HTTPS enabled (certfile: %s)", ssl_certfile)
            StandaloneApplication(app, gunicorn_opts).run()
    finally:
        _stop_debug_worker()
