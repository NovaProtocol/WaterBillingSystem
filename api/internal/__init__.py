from __future__ import annotations

import os
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import desc
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash

from app import db
from models import (
    ApiKey,
    BackgroundTask,
    Billing,
    Config,
    Customer,
    ManagementLog,
    MeterReading,
    NfcTag,
    Staff,
    XenditTransaction,
)
from pricing import PRICING_TIERS, compute_water_bill
from billing_service import ensure_penalty
from customer_service import (
    create_customer,
    get_customer_by_number,
    get_customer_or_404,
    list_customers,
    toggle_active,
    update_customer,
)
from services.payment_service import (
    compute_cashier_tally,
    compute_nav_dates,
    drop_payment as service_drop_payment,
    parse_date_range,
    recalc_cumulative_balance,
    submit_payment as service_submit_payment,
)
from reading_service import (
    drop_reading as service_drop_reading,
    edit_reading as service_edit_reading,
)


api_internal_bp = Blueprint("api_internal", __name__, url_prefix="/api/internal")

BACKUP_DIR = Path("/app/db_backups")
