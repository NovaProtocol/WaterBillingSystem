"""Database migrations for schema changes (async)."""
from __future__ import annotations

from sqlalchemy import inspect, text

from db_async import session


async def run_migrations() -> None:
    """Run any pending database migrations."""
    conn = await session().connection()

    def _columns(sync_conn) -> list[str]:
        return [c["name"] for c in inspect(sync_conn).get_columns("customers")]

    columns = await conn.run_sync(_columns)

    if "meter_serial_number" not in columns:
        await session().execute(text(
            "ALTER TABLE customers ADD COLUMN meter_serial_number VARCHAR(64) NULL"
        ))
        await session().commit()
        print("[migrate] Added meter_serial_number column to customers table.")
    else:
        print("[migrate] meter_serial_number column already exists.")

    if "total_due" not in columns:
        await session().execute(text(
            "ALTER TABLE customers ADD COLUMN total_due DECIMAL(10,2) NOT NULL DEFAULT 0.00"
        ))
        await session().commit()
        print("[migrate] Added total_due column to customers table.")
    else:
        print("[migrate] total_due column already exists.")
