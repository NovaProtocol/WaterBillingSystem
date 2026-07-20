"""Database migrations for schema changes."""
from __future__ import annotations

import sqlalchemy as sa


def run_migrations():
    """Run any pending database migrations."""
    from app import db

    inspector = sa.inspect(db.engine)
    columns = [c["name"] for c in inspector.get_columns("customers")]

    if "meter_serial_number" not in columns:
        db.session.execute(sa.text(
            "ALTER TABLE customers ADD COLUMN meter_serial_number VARCHAR(64) NULL"
        ))
        db.session.commit()
        print("[migrate] Added meter_serial_number column to customers table.")
    else:
        print("[migrate] meter_serial_number column already exists.")

    if "total_due" not in columns:
        db.session.execute(sa.text(
            "ALTER TABLE customers ADD COLUMN total_due DECIMAL(10,2) NOT NULL DEFAULT 0.00"
        ))
        db.session.commit()
        print("[migrate] Added total_due column to customers table.")
    else:
        print("[migrate] total_due column already exists.")
