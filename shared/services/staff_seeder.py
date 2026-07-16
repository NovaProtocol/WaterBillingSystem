from __future__ import annotations

import binascii
import hashlib
import os

from apps import db
from models import Staff


PREREQ_USERNAMES = frozenset({"superuser", "xendit"})


def ensure_prereq_staff() -> None:
    existing_superuser = Staff.query.filter_by(username="superuser").first()
    if not existing_superuser:
        salt = hashlib.sha256(os.urandom(60)).hexdigest().encode("ascii")
        pwdhash = hashlib.pbkdf2_hmac("sha512", b"superuser", salt, 100000)
        db.session.add(Staff(
            username="superuser",
            name="Superuser",
            password=salt + binascii.hexlify(pwdhash),
            can_read_meters=True, can_accept_payment=True,
            can_enroll_customer=True, can_drop_reading=True,
            can_drop_payment=True, can_enroll_staff=True,
            can_manage_billing=True,
            is_active=True,
        ))

    existing_xendit = Staff.query.filter_by(username="xendit").first()
    if not existing_xendit:
        db.session.add(Staff(
            username="xendit",
            name="Xendit",
            password=b"",
            can_accept_payment=True,
            can_manage_billing=True,
            can_drop_payment=True,
            is_active=True,
        ))


    db.session.commit()

def delete_non_prereq_staff() -> None:
    Staff.query.filter(Staff.username.notin_(PREREQ_USERNAMES)).delete(
        synchronize_session="fetch"
    )
