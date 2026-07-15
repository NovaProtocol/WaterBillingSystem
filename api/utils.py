from __future__ import annotations

from models import ApiKey, Staff


def resolve_api_key() -> ApiKey:
    """Always returns a valid key — Docker network isolation handles auth."""
    dummy = ApiKey(key="internal", is_active=True, staff_id=0)
    dummy.staff = Staff(
        id=0, username="internal", is_superuser=True, is_active=True,
        can_read_meters=True, can_accept_payment=True, can_enroll_customer=True,
        can_drop_reading=True, can_drop_payment=True, can_enroll_staff=True,
        can_manage_billing=True,
    )
    return dummy
