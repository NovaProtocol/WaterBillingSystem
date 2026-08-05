from __future__ import annotations

import datetime as dt
import enum

from flask_login import UserMixin

from apps import db, login_manager


class Staff(db.Model, UserMixin):

    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False, default="")
    password = db.Column(db.LargeBinary, nullable=False)
    email = db.Column(db.String(128), nullable=True)
    contact_number = db.Column(db.String(32), nullable=True)

    can_read_meters = db.Column(db.Boolean, default=False)
    can_accept_payment = db.Column(db.Boolean, default=False)
    can_enroll_customer = db.Column(db.Boolean, default=False)
    can_drop_reading = db.Column(db.Boolean, default=False)
    can_drop_payment = db.Column(db.Boolean, default=False)
    can_enroll_staff = db.Column(db.Boolean, default=False)
    can_manage_billing = db.Column(db.Boolean, default=False)

    is_active = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    last_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def __repr__(self) -> str:
        return str(self.name or self.username)


@login_manager.user_loader
def staff_loader(id: int | str) -> Staff | None:
    return Staff.query.filter_by(id=id).first()


class Customer(db.Model):

    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(db.Integer, unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=True)
    address = db.Column(db.Text(), nullable=True)
    contact_number = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(128), nullable=True)
    x_coordinate = db.Column(db.Float, nullable=True)
    y_coordinate = db.Column(db.Float, nullable=True)
    phase = db.Column(db.String(64), nullable=True)
    block = db.Column(db.String(64), nullable=True)
    street = db.Column(db.String(128), nullable=True)
    cumulative_balance = db.Column(db.Numeric(10, 2), default=0.00)
    total_due = db.Column(db.Numeric(10, 2), default=0.00)
    meter_serial_number = db.Column(db.String(64), nullable=True, index=True)
    max_meter_value = db.Column(db.Numeric(10, 2), default=99999.00)

    is_active = db.Column(db.Boolean, default=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    date_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Customer {self.customer_number}>"


class MeterReading(db.Model):

    __tablename__ = "meter_readings"

    id = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(
        db.Integer,
        db.ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    reading_value = db.Column(db.Numeric(10, 2), nullable=False)
    token_id = db.Column(
        db.Integer, db.ForeignKey("api_keys.id"), nullable=False, index=True
    )
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    date_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    customer = db.relationship(
        "Customer", backref=db.backref("meter_readings", lazy=True)
    )
    token = db.relationship("ApiKey", backref=db.backref("meter_readings", lazy=True))

    def __repr__(self) -> str:
        return f"<MeterReading {self.customer_number} {self.reading_value}>"


class Billing(db.Model):

    __tablename__ = "billings"

    id = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(
        db.Integer,
        db.ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    reading_id = db.Column(
        db.Integer, db.ForeignKey("meter_readings.id"), nullable=True
    )

    previous_reading_value = db.Column(db.Numeric(10, 2), nullable=True)
    current_reading_value = db.Column(db.Numeric(10, 2), nullable=True)
    consumption = db.Column(db.Numeric(10, 2), nullable=True)

    billed_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    penalty = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    paid_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    carryover_offset = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    is_paid = db.Column(db.Boolean, nullable=False, default=False)

    receipt_number = db.Column(db.String(64), nullable=True)
    cashier_id = db.Column(
        db.Integer, db.ForeignKey("staff.id"), nullable=True, index=True
    )
    payment_timestamp = db.Column(db.DateTime, nullable=True)
    date_paid = db.Column(db.DateTime, nullable=True)

    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    date_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    customer = db.relationship(
        "Customer", backref=db.backref("billings", lazy=True)
    )
    reading = db.relationship(
        "MeterReading", backref=db.backref("billings", lazy=True)
    )
    cashier = db.relationship(
        "Staff", backref=db.backref("billings", lazy=True)
    )

    def __repr__(self) -> str:
        return f"<Billing {self.customer_number} {'Paid' if self.is_paid else 'Unpaid'}>"


class ApiKey(db.Model):

    __tablename__ = "api_keys"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False)
    label = db.Column(db.String(128), nullable=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    last_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    staff = db.relationship("Staff", backref=db.backref("api_keys", lazy=True))

    def __repr__(self) -> str:
        return f"<ApiKey {self.label or self.key[:16]}>"


class NfcTag(db.Model):

    __tablename__ = "nfc_tags"

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(64), unique=True, nullable=False)
    customer_number = db.Column(
        db.Integer,
        db.ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    enrolled_by_id = db.Column(
        db.Integer, db.ForeignKey("staff.id"), nullable=False
    )
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    last_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    customer = db.relationship(
        "Customer", backref=db.backref("nfc_tags", lazy=True)
    )
    enrolled_by = db.relationship("Staff", backref=db.backref("nfc_tags", lazy=True))

    def __repr__(self) -> str:
        return f"<NfcTag {self.uid} -> {self.customer_number}>"


class ActionType(enum.StrEnum):
    DUPLICATE = "duplicate"
    DROP_PAYMENT = "drop_payment"
    EDIT_PAYMENT = "edit_payment"
    DROP_READING = "drop_reading"
    EDIT_READING = "edit_reading"


class ManagementLog(db.Model):

    __tablename__ = "management_logs"

    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
    action_type = db.Column(db.String(64), nullable=False)
    target_type = db.Column(db.String(64), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    customer_number = db.Column(
        db.Integer,
        db.ForeignKey("customers.customer_number"),
        nullable=True,
        index=True,
    )
    details = db.Column(db.Text(), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    date_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    staff = db.relationship(
        "Staff", backref=db.backref("management_logs", lazy=True)
    )


class Config(db.Model):

    __tablename__ = "app_config"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(128), unique=True, nullable=False)
    value = db.Column(db.Text(), nullable=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    date_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Config {self.key}={self.value!r}>"


class PaymentMethod(db.Model):

    __tablename__ = "payment_methods"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False, index=True)
    label = db.Column(db.String(128), nullable=False)
    provider = db.Column(db.String(32), nullable=True)
    channel_code = db.Column(db.String(64), nullable=True)
    fee_percent = db.Column(db.Numeric(5, 2), nullable=True)
    fee_flat = db.Column(db.Numeric(10, 2), nullable=True)
    fee_minimum = db.Column(db.Numeric(10, 2), nullable=True)
    xendit_fee = db.Column(db.Numeric(10, 2), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)

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


class XenditTransaction(db.Model):

    __tablename__ = "xendit_transactions"

    id = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(
        db.Integer,
        db.ForeignKey("customers.customer_number"),
        nullable=False,
        index=True,
    )
    xendit_pr_id = db.Column(db.String(128), unique=True, nullable=False, index=True)
    external_id = db.Column(db.String(256), unique=True, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    base_amount = db.Column(db.Numeric(10, 2), nullable=True)
    fee_amount = db.Column(db.Numeric(10, 2), nullable=True)
    fee_rate = db.Column(db.Numeric(5, 2), nullable=True)
    payment_method = db.Column(db.String(32), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="PENDING")
    receipt_number = db.Column(db.String(64), nullable=True)
    billing_receipt = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.Text(), nullable=True)
    reversed_at = db.Column(db.DateTime, nullable=True)
    xendit_payment_id = db.Column(db.String(128), nullable=True)
    date_created = db.Column(db.DateTime, default=dt.datetime.utcnow)
    date_modified = db.Column(
        db.DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    customer = db.relationship(
        "Customer", backref=db.backref("xendit_transactions", lazy=True)
    )

    def __repr__(self) -> str:
        return f"<XenditTransaction {self.xendit_pr_id} {self.status}>"


class BackgroundTask(db.Model):

    __tablename__ = "background_tasks"

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(64), nullable=False, index=True)
    params = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="queued", index=True)
    progress = db.Column(db.Float, nullable=False, default=0.0)
    messages = db.Column(db.JSON, nullable=False, default=lambda: [])
    result = db.Column(db.JSON, nullable=True)
    title = db.Column(db.String(256), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=True)
    started_at = db.Column(db.DateTime, nullable=True)
    finished_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=dt.datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    @classmethod
    def enqueue(
        cls,
        task_type: str,
        params: dict | None = None,
        title: str | None = None,
        scheduled_at: dt.datetime | None = None,
    ) -> BackgroundTask:
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
        existing = cls.query.filter(
            cls.task_type == task_type,
            cls.status.in_(["queued", "running"]),
        ).first()
        if existing:
            return None
        return cls.enqueue(task_type=task_type, params=params, title=title, scheduled_at=scheduled_at)

    def __repr__(self) -> str:
        return f"<BackgroundTask {self.id} {self.task_type} {self.status}>"
