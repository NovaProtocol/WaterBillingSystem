from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
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
_debug_worker_lock = threading.Lock()
_DEBUG_WORKER_PIDFILE = Path("/tmp/billserver-debug-worker.pid")

parser = argparse.ArgumentParser(description="BillServer")
parser.add_argument(
    "--deployment_type",
    choices=["DEBUG", "PRODUCTION"],
    default=os.environ.get("DEPLOYMENT_TYPE"),
    help="Run mode ($DEPLOYMENT_TYPE env var, required)",
)
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

    # pyscss is incompatible with Python 3.14's re module.
    # Pre-compile CSS during Docker build instead.
    try:
        from scss.compiler import compile_string
    except ImportError:
        logger.warning("SCSS compiler not available, skipping CSS build")
        return

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
            css = compile_string(scss_content, output_style="compressed")
            with open(css_path, "w") as f:
                f.write(css)
            logger.info("Compiled %s", css_name)
        except Exception as e:
            logger.warning("Failed to compile %s: %s", fname, e)


def _ensure_prerequisites(app: Flask) -> None:
    from apps.models import Staff
    from apps.authentication.util import hash_pass

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

        xendit_user = Staff.query.filter_by(username="xendit").first()
        if not xendit_user:
            xendit_user = Staff(
                username="xendit",
                name="Xendit",
                password=b"",
                can_accept_payment=True,
                can_manage_billing=True,
                can_drop_payment=True,
            )
            db.session.add(xendit_user)
            db.session.commit()
            logger.info("Created system xendit user (automated payments)")
        else:
            xendit_user.password = b""
            xendit_user.can_accept_payment = True
            xendit_user.can_manage_billing = True
            xendit_user.can_drop_payment = True
            db.session.commit()
            logger.info("Xendit system user verified")

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

        from apps.billing import api as billing_api
        billing_api.reconcile_xendit_payments(app)


def _start_debug_worker() -> subprocess.Popen | None:
    global _debug_worker_proc
    with _debug_worker_lock:
        if _debug_worker_proc is not None:
            return _debug_worker_proc
        try:
            if _DEBUG_WORKER_PIDFILE.exists():
                pid = int(_DEBUG_WORKER_PIDFILE.read_text().strip())
                os.kill(pid, 0)
                logger.warning("Debug worker already running (PID %d)", pid)
                return None
        except (ValueError, OSError):
            _DEBUG_WORKER_PIDFILE.unlink(missing_ok=True)
        worker_script = Path(__file__).resolve().parent / "apps" / "staff" / "debug_worker.py"
        if not worker_script.exists():
            logger.warning("Debug worker script not found: %s", worker_script)
            return None
        proc = subprocess.Popen([sys.executable, str(worker_script)])
        _debug_worker_proc = proc
        _DEBUG_WORKER_PIDFILE.write_text(str(proc.pid))
        logger.info("Debug worker started (PID %d)", proc.pid)
    return proc


def _stop_debug_worker() -> None:
    global _debug_worker_proc
    with _debug_worker_lock:
        if _debug_worker_proc is None:
            return
        try:
            _debug_worker_proc.terminate()
            _debug_worker_proc.wait(timeout=5)
        except Exception:
            try:
                _debug_worker_proc.kill()
                _debug_worker_proc.wait(timeout=3)
            except Exception:
                pass
        _debug_worker_proc = None
        _DEBUG_WORKER_PIDFILE.unlink(missing_ok=True)


# Start debug worker only in DEBUG mode.
# In production, each Gunicorn worker process would try to start one,
# causing duplicates. The debug dashboard is only available in DEBUG.
if DEBUG and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    _start_debug_worker()

if __name__ == "__main__":
    _compile_scss(app)
    _ensure_prerequisites(app)

    from apps.services.scheduler import start_scheduler
    start_scheduler(app)

    try:
        if DEBUG:
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
                "worker_class": "gthread",
                "workers": 2,
                "threads": 4,
                "accesslog": "-",
                "loglevel": "info",
                "capture_output": True,
                "enable_stdio_inheritance": True,
            }
            StandaloneApplication(app, gunicorn_opts).run()
    finally:
        _stop_debug_worker()
