# Meter Reading App

React Native Expo app for field staff. TypeScript strict.

**Tech**: Expo SDK ~56.0.14, React Native 0.85.3, TypeScript strict, `react-native-nfc-manager`, `@op-engineering/op-sqlite`.

## Navigation

Single native stack navigator with 6 registered screens plus 2 inline screens (Loading, Error):

| Screen | Params | Purpose |
|--------|--------|---------|
| Unauthenticated | none | Shown when no server URL/API key configured |
| Home | none | Dashboard with customer counts, filters |
| Reading | none | NFC reading + manual entry + bill estimate |
| CustomerDetail | `{customerNumber}` | Customer info + reading history + map |
| Map | none | Leaflet map of customer locations |
| Settings | none | Server config, QR scan API key, data reset |
| NfcEnroll | none | NFC tag enrollment/disenrollment wizard |

Inline: `LoadingScreen` (startup auth check), `ErrorScreen` (DB error with retry).

## Screens

### HomeScreen
Dashboard with dark header, customer count, filter bar (Phase/Block/Street), Map View and Start Reading buttons, gear icon for Settings, green Enroll button (permission-gated), unread list modal. Sync status indicator (idle/syncing/synced/error) with pending count. Tappable for manual sync, long-press for sync log modal.

### ReadingScreen (core)
Four states:
- **waiting**: NFC awaiting + manual entry option
- **found**: Customer info card, reading history pill, decimal input, bill estimate card, "Print Last Receipt" (disabled), submit button
- **summary**: Confirmation with offline notice, "Print Receipt" button (disabled)
- **error**: Error message + retry

Fetches pricing tiers on mount (24h cache in config). Checks server reachability via HEAD `/api/pricing`.

### SettingsScreen
Server IP + Server Port (separate fields), API key (QR scanner via `expo-camera`), history count text input (1-24), clear unsynced readings, reset all data (with confirmation).

### NfcEnrollScreen
Enrollment and disenrollment wizards with tag verification at every step (see nfc-security.md). 7 phases: search, verify, programming, done, error, disenrolling, disenroll_done.

## SQLite Database (`meterreading.db`)

5 tables via `@op-engineering/op-sqlite`:

### Config
Key-value: `serverUrl`, `apiKey`, `historyCount`, `lastSyncTime`, `lastServerWrite`, `nfc_pwd_secret`, `nfc_generation`, 7 permission flags, `pricing_tiers`, `pricing_fetched_at`, `nfc_has_pending`, `server_time`

### Customers
`customer_number` (PK TEXT), `name`, `address`, `contact_number`, `phase`, `block`, `street`, `x_coordinate`, `y_coordinate`, `last_reading_value`, `last_reading_timestamp`

### Readings
`id` (PK auto), `server_id` (unique, nullable), `customer_number` (TEXT), `reading_value`, `reader_id`, `timestamp`, `synced` (0/1), `rejected` (0/1)

### NFC Cache
`uid` (PK), `customer_number` (TEXT), `password` (derived, for offline auth)

### NFC Enrollments
`id` (PK auto), `uid` (TEXT), `customer_number` (TEXT), `synced` (0=pending, 1=synced)

## Background Sync

**File**: `src/services/syncService.ts`

Runs via `useSync()` hook in `App.tsx`. Triggered: on mount, every 10s while foreground, on app foreground event, on demand via `triggerSync()`.

### Sync Steps
1. **Fetch permissions**: `GET /api/key/info` → stores 7 permission flags in config
2. **Fetch NFC secrets**: `GET /api/nfc/config` → stores `nfc_pwd_secret` + `nfc_generation`. Clears cache if generation changed.
3. **Upload NFC enrollments**: `POST /api/nfc/sync` with pending enrollments
4. **Upload readings**: `POST /api/readings/sync` with unsynced readings. Marks synced/rejected per-reading.
5. **Download changes**: `GET /api/customers/changed?since=<lastSyncTime>`. For each batch of 500, fetches `GET /api/readings/bulk?customer_numbers=...&limit=<historyCount>`. Request pipelining for speed.
6. **Replace local data**: Atomic per-customer: delete old readings, insert fresh.
7. **Update `lastSyncTime`** from server response.
8. **Cleanup**: Delete synced NFC enrollment records.

### Resync Functions
- `resyncNfc()` — clears NFC cache, re-fetches all tags from server, recomputes passwords
- `resyncReadings()` — clears all customers/readings, triggers full re-download

## Type Conversions

API `customer_number` is `number`; SQLite stores it as `TEXT`. Sync service converts:
- Upload: `Number(r.customer_number)`
- Download: `String(data.customer.customer_number)`
- NFC enrollment: `Number(accountNumber)` for API

## Offline Flow
Readings saved locally with `synced=0` when offline. `checkServerReachable()` pings HEAD `/api/pricing` with 5s timeout. Shows "Saved offline — will sync later" in submit summary.

## Components (12)

| Component | Purpose |
|-----------|---------|
| `NfcScanner.tsx` | Background NFC read loop with auto-retry, PWD_AUTH auth |
| `QrScanner.tsx` | QR code scanner for API token input |
| `ReadingInput.tsx` | Decimal-only meter value input |
| `BillEstimateCard.tsx` | Expandable pricing tier breakdown |
| `ReadingHistoryPill.tsx` | Last reading card + history modal |
| `CustomerInfoCard.tsx` | Customer name/number/address |
| `CustomerFilterBar.tsx` | Phase/block/street filter chips |
| `FilterPickerModal.tsx` | Bottom sheet picker |
| `UnreadListModal.tsx` | Slide-up list of unread customers |
| `SubmitSummary.tsx` | Confirmation with offline notice |
| `ErrorBoundary.tsx` | Error boundary wrapping the app |
| `CustomerCountCard.tsx` | Customer count display card |

## API Endpoint Mismatches

The app uses these paths that differ from current API routes:

| App Calls | Actual API Endpoint |
|-----------|-------------------|
| `/api/nfc/config` | `/api/config/nfc_secret` |
| `/api/nfc/tags` | `/api/customer/all/nfc` |
| `/api/pricing` | `/api/config/pricing` |
| `/api/key/info` | `/api/staff/info` |
| `/api/readings/sync` | Not implemented (use per-customer `/api/customer/<n>/reading/new`) |
| `/api/readings/bulk` | Not implemented (use change detection + per-customer) |
| `/api/nfc/sync` | Not implemented (use per-customer NFC create) |
