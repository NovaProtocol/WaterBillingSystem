from __future__ import annotations

import os

from shared.grpc_client import list_customers_via_grpc
from shared.http_client import make_client

# Staff billing detail (get_customer with consumption/bill_breakdown) must use
# HTTP: gRPC GetCustomer is only core fields (see api_client comment).
# Search/list is gRPC-only with no HTTP fallback (fail loud).

get_customer_via_grpc = None  # type: ignore  # disabled: staff billing needs full HTTP payload

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = make_client(os.environ["API_BASE_URL"], container_name="staff-portal")
    return _client


def _staff_headers() -> dict[str, str]:
    try:
        import staff_auth as _sa  # late import to avoid cycle

        p = _sa.staff_payload()
        if p and p.get("id"):
            return {"X-Staff-ID": str(p["id"])}
    except Exception:
        pass
    return {}


async def _post(path, data=None):
    r = await _get_client().post(path, json=data or {}, headers=_staff_headers())
    r.raise_for_status()
    return r.json()


async def _get(path, params=None):
    r = await _get_client().get(path, params=params or {}, headers=_staff_headers())
    r.raise_for_status()
    return r.json()


async def _put(path, data=None):
    r = await _get_client().put(path, json=data or {}, headers=_staff_headers())
    r.raise_for_status()
    return r.json()


async def _delete(path):
    r = await _get_client().delete(path, headers=_staff_headers())
    r.raise_for_status()
    return r.json()


async def staff_login(username: str, password: str) -> dict:
    data = await _post("/api/staff/login", {"username": username, "password": password})
    return {"success": True, "staff": data}


async def get_dashboard_data() -> dict:
    customers = await _get("/api/customer/count")
    staff_list = await _get("/api/staff/all")
    return {
        "total_customers": customers.get("count", 0),
        "total_staff": len(staff_list.get("staff", [])),
    }


async def get_customer(customer_number: int, params: dict = None) -> dict:
    # Staff billing views need the full HTTP payload (consumption,
    # bill_breakdown, billing_items, etc). The gRPC GetCustomer stub
    # returns a short summary only and was causing undefined.toFixed
    # crashes in manage_billing/payments. Always use HTTP here.
    return await _get(f"/api/customer/{customer_number}", params)


def _is_name_query(s: str) -> bool:
    return bool(s) and all(c.isalpha() or c in " .-'" for c in s)


async def customer_search(query: str) -> list:
    """Search customers by number or name prefix. Proxies to API."""
    if not query or not query.strip():
        return []
    q = query.strip()
    if not (q.isdigit() or _is_name_query(q)):
        return [
            {
                "error": "mixed_input",
                "message": "Search by customer number (digits only) or name (letters only).",
            }
        ]
    data = await _get("/api/customer/all", {"q": q, "page": 1, "size": 50})
    return data.get("data", [])


async def customer_search_sort(
    q: str = "",
    sort_by: str = "customer_number",
    sort_dir: str = "asc",
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """Search, sort, paginate customers, gRPC is the exclusive transport, no HTTP fallback."""
    import grpc as _grpc  # local import so missing grpc surfaces as hard error, not silent

    try:
        data = await list_customers_via_grpc(  # type: ignore[misc]
            q=q, page=page, size=per_page, sort_by=sort_by, sort_dir=sort_dir
        )
    except _grpc.aio.AioRpcError:
        # Fail loud, do not fall back to HTTP, surface as 503 at caller
        raise
    if data is None:
        raise RuntimeError("grpc ListCustomers returned no data")
    return {
        "customers": data.get("customers", []),
        "page": data.get("page", page),
        "per_page": data.get("per_page", per_page),
        "total": data.get("total", 0),
        "pages": data.get("pages", 1),
    }


async def customer_lookup(query: str) -> dict:
    r = await _get("/api/customer/all", {"q": query, "size": 10})
    return r.get("data", [])


async def get_customers(page: int = 1, per_page: int = 50) -> dict:
    r = await _get("/api/customer/all", {"page": page, "size": per_page})
    return {
        "customers": r.get("data", []),
        "page": r.get("meta", {}).get("current_page", page),
        "per_page": r.get("meta", {}).get("page_size", per_page),
        "total": r.get("meta", {}).get("total_items", 0),
        "pages": r.get("meta", {}).get("total_pages", 1),
    }


async def create_customer(data: dict) -> dict:
    return await _post("/api/customer/new", data)


async def edit_customer(customer_id: int, data: dict) -> dict:
    customer_number = data.get("customer_number", str(customer_id))
    return await _put(f"/api/customer/update/{customer_number}", data)


async def toggle_customer_active(customer_number: int) -> dict:
    return await _delete(f"/api/customer/delete/{customer_number}")


async def clear_customer_nfc(customer_number: int) -> dict:
    return await _post(f"/api/customer/{customer_number}/nfc/delete")


async def submit_payment(data: dict) -> dict:
    customer_number = data.get("customer_number", 0)
    return await _post(f"/api/customer/{customer_number}/billing/new", data)


async def get_cashier_tally(
    period: str,
    cashier_id: int = 0,
    date: str = "",
    start_date: str = "",
    end_date: str = "",
    group_days: int = 1,
) -> dict:
    params = {"period": period, "group_days": group_days}
    if date:
        params["date"] = date
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return await _get(f"/api/staff/{cashier_id}/cashier-tally", params)


async def drop_reading(reading_id: int, data: dict) -> dict:
    customer_number = data.get("customer_number", 0)
    return await _post(
        f"/api/customer/{customer_number}/reading/drop",
        {"reading_id": reading_id, "reason": "Staff drop"},
    )


async def edit_reading(reading_id: int, data: dict) -> dict:
    customer_number = data.get("customer_number", 0)
    reading_value = data.get("reading_value", 0)
    return await _post(
        f"/api/customer/{customer_number}/reading/edit",
        {"reading_id": reading_id, "reading_value": reading_value},
    )


async def undo_payment(billing_id: int, reason: str = "") -> dict:
    return await _post(
        f"/api/customer/{billing_id}/billing/drop",
        {"billing_id": billing_id, "reason": reason or "Staff undo"},
    )


async def generate_api_key(staff_id: int = 1, data: dict = None) -> dict:
    return await _post(f"/api/staff/{staff_id}/api-key/generate", data or {})


async def revoke_api_key(staff_id: int, key_id: int) -> dict:
    return await _post(f"/api/staff/{staff_id}/api-key/{key_id}/revoke")


async def list_api_keys(staff_id: int = 1) -> dict:
    return await _get(f"/api/staff/{staff_id}/api-keys")


async def get_reading_logs(staff_id: int = 1) -> dict:
    return await _get(f"/api/staff/{staff_id}/reading-logs")


async def get_audit_logs(
    staff_id: int = 1, params: dict | None = None
) -> dict:
    return await _get(f"/api/staff/{staff_id}/audit-logs", params or {})


async def list_staff() -> dict:
    return await _get("/api/staff/all")


async def get_staff(staff_id: int) -> dict:
    return await _get(f"/api/staff/{staff_id}")


async def create_staff(data: dict) -> dict:
    return await _post("/api/staff/new", data)


async def edit_staff(staff_id: int, data: dict) -> dict:
    return await _post(f"/api/staff/{staff_id}/edit", data)
