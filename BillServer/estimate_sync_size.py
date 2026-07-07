"""
Estimate full sync data size by hitting the actual API endpoints.

Measures real HTTP response sizes for /api/customers/changed and /api/readings/bulk.

Usage (BillServer must be running on port 5005):

    source .venv/bin/activate
    python3 estimate_sync_size.py

Or with custom URL:
    python3 estimate_sync_size.py https://192.168.18.52:5005
"""

import json
import math
import ssl
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://localhost:5005"

# Use the dev API key from the database
API_KEY = "CRDC-1A1F8C1E44A433DE3928271263E9A5A7"

def api(method: str, path: str, body: bytes | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    if BASE.startswith("https://localhost") or BASE.startswith("https://127.0.0.1"):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        data = resp.read()
        return resp.status, data

# Step 1: Get all changed customers (since=0 = all)
print("Fetching changed customers since epoch...")
status, changed_data = api("GET", "/api/customers/changed?since=0")
changed = json.loads(changed_data)
customer_numbers = changed.get("customer_numbers", [])
total = len(customer_numbers)
print(f"  {total} customers changed")

# Step 2: Download in batches of 500 and measure each response size
batch_size = 500
batches = [customer_numbers[i:i+batch_size] for i in range(0, total, batch_size)]
total_payload_bytes = 0

sample_responses = []
for idx, batch in enumerate(batches):
    joined = ",".join(batch)
    status, bulk_data = api("GET", f"/api/readings/bulk?customer_numbers={joined}&limit=48")
    total_payload_bytes += len(bulk_data)
    if idx < 3 or idx == len(batches) - 1:
        sample_responses.append(len(bulk_data))
    print(f"  Batch {idx+1}/{len(batches)}: {len(bulk_data):>8,} bytes ({len(batch)} customers)")
    if idx >= 4 and len(batches) > 8:
        print(f"  ... ({len(batches) - idx - 1} batches remaining, estimating)")
        # Estimate remaining batches
        avg = total_payload_bytes / (idx + 1)
        remaining = len(batches) - (idx + 1)
        total_payload_bytes += int(avg * remaining)
        print(f"  Estimated remaining {remaining} batches × ~{avg:,.0f} bytes")
        break

# Step 3: Count changed endpoint size
changed_size = len(changed_data)

# Step 4: Tally
data_kb = total_payload_bytes / 1024
data_mb = data_kb / 1024
http_overhead_kb = len(batches) * 2  # ~2KB HTTP overhead per request

# Also account for the changed request
total_data_kb = (total_payload_bytes + changed_size) / 1024 + http_overhead_kb
total_data_mb = total_data_kb / 1024

print()
print("=" * 60)
print("  FULL SYNC SIZE (REAL API MEASUREMENT)")
print("=" * 60)
print(f"  Customers:           {total:,}")
print(f"  Batches:             {len(batches)}")
print(f"  Changed req:         {changed_size:>8,} bytes")
print(f"  Bulk payload total:  {total_payload_bytes:>8,} bytes")
print(f"                        {data_kb:>7,.1f} KB")
print(f"                        {data_mb:>7,.2f} MB")
print(f"  HTTP overhead:       {http_overhead_kb:>7,.0f} KB")
print(f"  ────────────────────────────────────────")
print(f"  GRAND TOTAL:         {total_data_kb:>7,.1f} KB ({total_data_mb:.2f} MB)")
print()
if sample_responses:
    avg_batch = sum(sample_responses[:min(3, len(sample_responses))]) / min(3, len(sample_responses))
    print(f"  Sample batch sizes: {', '.join(f'{s:,}' for s in sample_responses)} bytes")
    print(f"  Avg per batch:      {avg_batch:,.0f} bytes")
    per_customer = total_payload_bytes / total if total else 0
    print(f"  Avg per customer:   {per_customer:,.0f} bytes")
