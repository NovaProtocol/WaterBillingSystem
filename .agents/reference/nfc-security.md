# NFC Tags & Security

NTAG215 clone tags with PWD_AUTH (password authentication) protection.

## Full NFC Reading Flow

```
1. Reader taps phone to meter → NFC tag detected
2. Phone reads UID from tag pages 0-1 (7 bytes, always public)
3. Phone looks up UID in local nfc_cache → customer_number + cached password
4. Phone computes expected password: SHA256(nfc_pwd_secret + uid)[:4] (first 4 bytes as hex)
5. Phone authenticates via PWD_AUTH command (0x1b):
   Try: computed password → cached password → factory FFFF → factory 0000
6. Phone reads customer data from protected pages 7-18
7. Phone verifies customer number matches cache (tampering detection)
8. Phone looks up full customer info from local customers table
9. ReadingScreen displays customer info + reading input
10. Staff enters meter reading value, submits
11. Reading saved locally (synced=0 if offline)
12. Background sync pushes reading to server
13. Server creates MeterReading + auto-generates Billing record
```

## NFC Tag Memory Layout

NTAG215 has 135 pages (4 bytes each). Protected pages (4+) require password authentication.

```
Page 0x00: UID bytes 0-2 / BCC0              ← factory, always public
Page 0x01: UID bytes 3-6                      ← factory, always public
Page 0x02-0x03: internal / lock / OTP
Page 0x04: RESERVED (MIRROR auto-copies UID)  ← AUTH0 boundary
Page 0x05-0x06: unused
Page 0x07+: customer number (ASCII, 4-byte padded, null-terminated)
...
Page 0x83: CFG0 = [04:00:00:04]               ← Byte 3 = AUTH0=4, Byte 0 = MIRROR 0x04
Page 0x84: CFG1 = [80:00:00:00]               ← Byte 0 = 0x80 → PROT=1 (read+write protected)
Page 0x85: PWD = 4 bytes                      ← derived password
Page 0x86: PACK = [00:00:00:00]               ← password acknowledge response
```

## Password Derivation

Server provides `nfc_pwd_secret` (64 hex chars = 256 bits) via `GET /api/config/nfc_secret`.

```
PWD = first 4 bytes of SHA-256(secret + uid), formatted as 8 lowercase hex chars
```

Computed independently on phone (for reading) and server (for sync). Cached in local `nfc_cache` for offline use.

If server rotates the secret (increments `nfc_generation`), the phone detects the change and clears its nfc_cache on next sync.

## Enrollment Flow

Writing a new NFC tag via `NfcEnrollScreen`:

1. Scan tag → verify NTAG215 (GET_VERSION, checks version[2]=0x04)
2. Read UID → check not already enrolled locally
3. Authenticate with factory passwords (FFFF, then 0000)
4. Write customer data to pages 7+ (4 bytes per page, padded)
5. Verify by reading back and comparing
6. Write PWD to page 133, PACK to page 134
7. Verify PWD+PACK: authenticate with new password, check PACK = [0x00, 0x00]
8. Write CFG0 `[04:00:00:04]` to page 131 → AUTH0=4, enables password auth
9. Verify CFG0 readback
10. Write CFG1 `[80:00:00:00]` to page 132 → PROT=1 (read+write protected)
11. Verify CFG1 readback
12. Final verification: re-authenticate, re-read customer data
13. Save to local DB (nfc_cache + nfc_enrollments with synced=0)
14. Sync enrollment to server via background sync (`POST /api/nfc/sync` — **not implemented in the API yet**; the mobile contract is under rework, see rest-api.md)

## Disenrollment Flow

Erasing a tag:

1-5: Same as enrollment (verify NTAG215, read UID, compute password)
6. Restore factory config: CFG0 `[04:00:00:FF]`, CFG1 `[00:05:00:00]`
7. Re-authenticate
8. Clear data pages 5-31 (write zeros, retry with re-auth on failure)
9. Reset PWD to `[00:00:00:00]`, PACK to `[00:00:00:00]`
10. Remove from local DB (nfc_cache + nfc_enrollments)
