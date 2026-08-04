from __future__ import annotations

import datetime as dt
import enum

from flask_login import UserMixin
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import backref, relationship

from apps import login_manager
from db_async import Base


@login_manager.user_loader
def staff_loader(id: int | str) -> Staff | None:
    return Staff.query.filter_by(id=id).first()


class Staff(Base, UserMixin):

    __tablename__ = "staff"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False)
    name = Column(String(128), nullable=False, default="")
    password = Column(LargeBinary, nullable=False)
    email = Column(String(128), nullable=True)
    contact_number = Column(String(32), nullable=True)

    can_read_meters = Column(Boolean, default=False)
    can_accept_payment = Column(Boolean, default=False)
    can_enroll_customer = Column(Boolean, default=False)
    can_drop_reading = Column(Boolean, default=False)
    can_drop_payment = Column(Boolean, default=False)
    can_enroll_staff = Column(Boolean, default=False)
    can_manage_billing = Column(Boolean, default=False)

    is_active = Column(Boolean, default=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    last_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def __repr__(self) -> str:
        return str(self.name or self.username)


class Customer(Base):

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True)
    customer_number = Column(Integer, unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=True)
    address = Column(Text(), nullable=True)
    contact_number = Column(String(32), nullable=True)
    email = Column(String(128), nullable=True)
    x_coordinate = Column(Float, nullable=True)
    y_coordinate = Column(Float, nullable=True)
    phase = Column(String(64), nullable=True)
    block = Column(String(64), nullable=True)
    street = Column(String(128), nullable=True)
    cumulative_balance = Column(Numeric(10, 2), default=0.00)
    total_due = Column(Numeric(10, 2), default=0.00)
    meter_serial_number = Column(String(64), nullable=True, index=True)
    max_meter_value = Column(Numeric(10, 2), default=99999.00)

    is_active = Column(Boolean, default=True)
    deleted_at = Column(DateTime, nullable=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    date_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Customer {self.customer_number}>"


class MeterReading(Base):

    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True)
    customer_number = Column(
        Integer,
        ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    reading_value = Column(Numeric(10, 2), nullable=False)
    token_id = Column(
        Integer, ForeignKey("api_keys.id"), nullable=False, index=True
    )
    timestamp = Column(DateTime, nullable=False, index=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    date_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    customer = relationship(
        "Customer", backref=backref("meter_readings", lazy=True)
    )
    token = relationship("ApiKey", backref=backref("meter_readings", lazy=True))

    def __repr__(self) -> str:
        return f"<MeterReading {self.customer_number} {self.reading_value}>"


class Billing(Base):

    __tablename__ = "billings"

    id = Column(Integer, primary_key=True)
    customer_number = Column(
        Integer,
        ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    reading_id = Column(
        Integer, ForeignKey("meter_readings.id"), nullable=True
    )

    previous_reading_value = Column(Numeric(10, 2), nullable=True)
    current_reading_value = Column(Numeric(10, 2), nullable=True)
    consumption = Column(Numeric(10, 2), nullable=True)

    billed_amount = Column(Numeric(10, 2), nullable=False, default=0)
    penalty = Column(Numeric(10, 2), nullable=False, default=0)
    paid_amount = Column(Numeric(10, 2), nullable=False, default=0)
    carryover_offset = Column(Numeric(10, 2), nullable=False, default=0)
    is_paid = Column(Boolean, nullable=False, default=False)

    receipt_number = Column(String(64), nullable=True)
    cashier_id = Column(
        Integer, ForeignKey("staff.id"), nullable=True, index=True
    )
    payment_timestamp = Column(DateTime, nullable=True)
    date_paid = Column(DateTime, nullable=True)

    date_created = Column(DateTime, default=dt.datetime.utcnow)
    date_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
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

    id = Column(Integer, primary_key=True)
    key = Column(String(128), unique=True, nullable=False)
    label = Column(String(128), nullable=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    last_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    staff = relationship("Staff", backref=backref("api_keys", lazy=True))

    def __repr__(self) -> str:
        return f"<ApiKey {self.label or self.key[:16]}>"


class NfcTag(Base):

    __tablename__ = "nfc_tags"

    id = Column(Integer, primary_key=True)
    uid = Column(String(64), unique=True, nullable=False)
    customer_number = Column(
        Integer,
        ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    enrolled_by_id = Column(
        Integer, ForeignKey("staff.id"), nullable=False
    )
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    last_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
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

    id = Column(Integer, primary_key=True)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    action_type = Column(String(64), nullable=False)
    target_type = Column(String(64), nullable=False)
    target_id = Column(Integer, nullable=False)
    customer_number = Column(
        Integer,
        ForeignKey("customers.customer_number"),
        nullable=True,
        index=True,
    )
    details = Column(Text(), nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    date_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    staff = relationship(
        "Staff", backref=backref("management_logs", lazy=True)
    )


class Config(Base):

    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(Text(), nullable=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    date_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Config {self.key}={self.value!r}>"


class PaymentMethod(Base):

    __tablename__ = "payment_methods"

    id = Column(Integer, primary_key=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    label = Column(String(128), nullable=False)
    provider = Column(String(32), nullable=True)
    channel_code = Column(String(64), nullable=True)
    fee_percent = Column(Numeric(5, 2), nullable=True)
    fee_flat = Column(Numeric(10, 2), nullable=True)
    fee_minimum = Column(Numeric(10, 2), nullable=True)
    xendit_fee = Column(Numeric(10, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    date_created = Column(DateTime, default=dt.datetime.utcnow)

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

    id = Column(Integer, primary_key=True)
    customer_number = Column(
        Integer,
        ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    xendit_pr_id = Column(String(128), unique=True, nullable=False, index=True)
    external_id = Column(String(256), unique=True, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    base_amount = Column(Numeric(10, 2), nullable=True)
    fee_amount = Column(Numeric(10, 2), nullable=True)
    fee_rate = Column(Numeric(5, 2), nullable=True)
    payment_method = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="PENDING")
    receipt_number = Column(String(64), nullable=True)
    billing_receipt = Column(String(64), nullable=True)
    error_message = Column(Text(), nullable=True)
    reversed_at = Column(DateTime, nullable=True)
    xendit_payment_id = Column(String(128), nullable=True)
    date_created = Column(DateTime, default=dt.datetime.utcnow)
    date_modified = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    customer = relationship(
        "Customer", backref=backref("xendit_transactions", lazy=True)
    )

    def __repr__(self) -> str:
        return f"<XenditTransaction {self.xendit_pr_id} {self.status}>"


class BackgroundTask(Base):

    __tablename__ = "background_tasks"

    id = Column(Integer, primary_key=True)
    task_type = Column(String(64), nullable=False, index=True)
    params = Column(JSON, nullable=True)
    status = Column(String(16), nullable=False, default="queued", index=True)
    progress = Column(Float, nullable=False, default=0.0)
    messages = Column(JSON, nullable=False, default=lambda: [])
    result = Column(JSON, nullable=True)
    title = Column(String(256), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    @classmethod
    def enqueue(
        cls,
        task_type: str,
        params: dict | None = None,
        title: str | None = None,
        scheduled_at: dt.datetime | None = None,
    ) -> BackgroundTask:
        from apps import db

        task = cls(
            task_type=task_type,
            params=params or {},
            title=title or task_type,
            status="queued",
            scheduled_at=scheduled_at,
        )
        db.session.add(task)
        db.session.commit()
        return task

    @classmethod
    def enqueue_unique(
        cls,
        task_type: str,
        params: dict | None = None,
        title: str | None = None,
        scheduled_at: dt.datetime | None = None,
    ) -> BackgroundTask | None:
        from apps import db

        existing = cls.query.filter(
            cls.task_type == task_type,
            cls.status.in_(["queued", "running"]),
        ).first()
        if existing:
            return None
        return cls.enqueue(task_type=task_type, params=params, title=title, scheduled_at=scheduled_at)

    def __repr__(self) -> str:
        return f"<BackgroundTask {self.id} {self.task_type} {self.status}>"
