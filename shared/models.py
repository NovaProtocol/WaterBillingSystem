from __future__ import annotations

import datetime as dt
import decimal
import enum

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from db_async import Base


def _utcnow() -> dt.datetime:
    # naive UTC to match existing rows and the codebase's comparisons
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Staff(Base):

    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    password: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(32), nullable=True)

    can_read_meters: Mapped[bool] = mapped_column(Boolean, default=False)
    can_accept_payment: Mapped[bool] = mapped_column(Boolean, default=False)
    can_enroll_customer: Mapped[bool] = mapped_column(Boolean, default=False)
    can_drop_reading: Mapped[bool] = mapped_column(Boolean, default=False)
    can_drop_payment: Mapped[bool] = mapped_column(Boolean, default=False)
    can_enroll_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_billing: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    last_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return str(self.name or self.username)


class Customer(Base):

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_number: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(Text(), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    x_coordinate: Mapped[float | None] = mapped_column(Float, nullable=True)
    y_coordinate: Mapped[float | None] = mapped_column(Float, nullable=True)
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    block: Mapped[str | None] = mapped_column(String(64), nullable=True)
    street: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cumulative_balance: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    total_due: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=0.00)
    meter_serial_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    max_meter_value: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=99999.00)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    date_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<Customer {self.customer_number}>"


class MeterReading(Base):

    __tablename__ = "meter_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_number: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_number"),
        nullable=False,
    )
    reading_value: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    token_id: Mapped[int] = mapped_column(
        ForeignKey("api_keys.id"), nullable=False, index=True
    )
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    date_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    customer = relationship(
        "Customer", backref=backref("meter_readings", lazy=True)
    )
    token = relationship("ApiKey", backref=backref("meter_readings", lazy=True))

    def __repr__(self) -> str:
        return f"<MeterReading {self.customer_number} {self.reading_value}>"


class Billing(Base):

    __tablename__ = "billings"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_number: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_number"),
        nullable=False,
    )
    reading_id: Mapped[int | None] = mapped_column(
        ForeignKey("meter_readings.id"), nullable=True
    )

    previous_reading_value: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    current_reading_value: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    consumption: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    billed_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    penalty: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    paid_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    carryover_offset: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    receipt_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cashier_id: Mapped[int | None] = mapped_column(
        ForeignKey("staff.id"), nullable=True, index=True
    )
    payment_timestamp: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    date_paid: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    date_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    customer = relationship(
        "Customer", backref=backref("billings", lazy=True)
    )
    reading = relationship(
        "MeterReading", backref=backref("billings", lazy=True)
    )
    cashier = relationship(
        "Staff", backref=backref("billings", lazy=True)
    )

    def __repr__(self) -> str:
        return f"<Billing {self.customer_number} {'Paid' if self.is_paid else 'Unpaid'}>"


class ApiKey(Base):

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    last_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    staff = relationship("Staff", backref=backref("api_keys", lazy=True))

    def __repr__(self) -> str:
        return f"<ApiKey {self.label or self.key[:16]}>"


class NfcTag(Base):

    __tablename__ = "nfc_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    uid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    customer_number: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    enrolled_by_id: Mapped[int] = mapped_column(
        ForeignKey("staff.id"), nullable=False
    )
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    last_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    customer = relationship(
        "Customer", backref=backref("nfc_tags", lazy=True)
    )
    enrolled_by = relationship("Staff", backref=backref("nfc_tags", lazy=True))

    def __repr__(self) -> str:
        return f"<NfcTag {self.uid} -> {self.customer_number}>"


class ActionType(enum.StrEnum):
    DUPLICATE = "duplicate"
    DROP_PAYMENT = "drop_payment"
    EDIT_PAYMENT = "edit_payment"
    DROP_READING = "drop_reading"
    EDIT_READING = "edit_reading"


class ManagementLog(Base):

    __tablename__ = "management_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_number: Mapped[int | None] = mapped_column(
        ForeignKey("customers.customer_number"),
        nullable=True,
        index=True,
    )
    details: Mapped[str | None] = mapped_column(Text(), nullable=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, index=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    date_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    staff = relationship(
        "Staff", backref=backref("management_logs", lazy=True)
    )


class Config(Base):

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text(), nullable=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    date_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    def __repr__(self) -> str:
        return f"<Config {self.key}={self.value!r}>"


class PaymentMethod(Base):

    __tablename__ = "payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fee_percent: Mapped[decimal.Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    fee_flat: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_minimum: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    xendit_fee: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    def fee_for(self, amount: float) -> float:
        fee = 0.0
        if self.fee_percent:
            fee += amount * float(self.fee_percent) / 100
        if self.fee_flat:
            fee += float(self.fee_flat)
        if self.fee_minimum and fee < float(self.fee_minimum):
            fee = float(self.fee_minimum)
        return round(fee, 2)

    def __repr__(self) -> str:
        return f"<PaymentMethod {self.code} ({self.label})>"


class XenditTransaction(Base):

    __tablename__ = "xendit_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_number: Mapped[int] = mapped_column(
        ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    xendit_pr_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    base_amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_amount: Mapped[decimal.Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    fee_rate: Mapped[decimal.Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    receipt_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    billing_receipt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    reversed_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    xendit_payment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date_created: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    date_modified: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    customer = relationship(
        "Customer", backref=backref("xendit_transactions", lazy=True)
    )

    def __repr__(self) -> str:
        return f"<XenditTransaction {self.xendit_pr_id} {self.status}>"


class BackgroundTask(Base):

    __tablename__ = "background_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    messages: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: [])
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=_utcnow, onupdate=_utcnow
    )

    @classmethod
    async def enqueue(
        cls,
        task_type: str,
        params: dict | None = None,
        title: str | None = None,
        scheduled_at: dt.datetime | None = None,
    ) -> BackgroundTask:
        from db_async import session_factory

        async with session_factory()() as s:
            task = cls(
                task_type=task_type,
                params=params or {},
                title=title or task_type,
                status="queued",
                scheduled_at=scheduled_at,
            )
            s.add(task)
            await s.commit()
            return task

    @classmethod
    async def enqueue_unique(
        cls,
        task_type: str,
        params: dict | None = None,
        title: str | None = None,
        scheduled_at: dt.datetime | None = None,
    ) -> BackgroundTask | None:
        from sqlalchemy import select

        from db_async import session_factory

        async with session_factory()() as s:
            existing = (
                await s.execute(
                    select(cls).where(
                        cls.task_type == task_type,
                        cls.status.in_(["queued", "running"]),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return None
            task = cls(
                task_type=task_type,
                params=params or {},
                title=title or task_type,
                status="queued",
                scheduled_at=scheduled_at,
            )
            s.add(task)
            await s.commit()
            return task

    def __repr__(self) -> str:
        return f"<BackgroundTask {self.id} {self.task_type} {self.status}>"
