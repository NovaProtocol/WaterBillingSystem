# Sync Architecture

**Offline-first**: data collected locally in SQLite, synchronized with BillServer in the background.

## Overview

```mermaid
sequenceDiagram
 participant App as MeterReadingApp
 participant DB as Local SQLite
 participant API as BillServer API

 Note over App: Every 10 seconds + on app foreground

 App->>API: GET /api/key/info
 API-->>App: {staff: {can_read_meters, can_enroll_customer, ...}}
 App->>DB: Store 7 permission flags in config

 App->>API: GET /api/nfc/config
 API-->>App: {nfc_pwd_secret, nfc_generation}
 App->>DB: Store nfc_pwd_secret, nfc_generation (clear cache if gen changed)

 App->>DB: getUnsyncedNfcEnrollments()
 App->>API: POST /api/nfc/sync
 API-->>App: {synced, total, errors}
 App->>DB: markNfcEnrollmentSynced()

 App->>DB: getUnsyncedReadings()
 App->>API: POST /api/readings/sync
 API-->>App: {synced, total, results: [{index, reading_id, customer_number}], errors: [{index, error}]}
 App->>DB: markReadingSynced(localId, result.reading_id)

 Note over App: lastSyncTime defaults to 0<br/>(first sync downloads everything)
 App->>DB: getIntSetting('lastSyncTime', 0)
 App->>API: GET /api/customers/changed?since=<lastSyncTime>
 API-->>App: {customer_numbers, server_time}

 loop 500 customers per batch (pipelined)
 App->>API: GET /api/readings/bulk?customer_numbers=...
 API-->>App: {customers: {"C1": {customer: {...}, readings: [...]}}}
 App->>DB: replaceCustomerData() per customer (individual commits)
 end

 App->>DB: setIntSetting('lastSyncTime', server_time)
 App->>DB: deleteSyncedNfcEnrollments()
```

## Sync Engine: `useSync()`

Custom React hook in `src/services/syncService.ts`.

### State Machine

```mermaid
graph LR
 IDLE["idle"] --> SYNCING["syncing"]
 SYNCING --> SYNCED["synced"]
 SYNCING --> ERROR["error"]
 SYNCED --> IDLE
 ERROR --> IDLE
```

### API

```typescript
const {
 syncStatus, // 'idle' | 'syncing' | 'synced' | 'error'
 triggerSync, // () => void, manual sync trigger
 lastError, // string | null
 lastSyncCount, // number
 resetSyncState, // () => void
 pendingCount, // number, unsynced readings
 serverTotal, // number, total customers on server
 lastSyncTime, // string | null
 localCount, // number, customers in local DB
 resyncNfc, // () => Promise<void>, force re-download NFC cache
 resyncReadings, // () => Promise<void>, clear local data and re-download all
 resyncing, // boolean, true during resync operation
} = useSync();
```

### Sync Triggers

| Trigger | Behavior |
|---|---|
| **On mount** | Runs `doSync()` immediately |
| **Polling** | Runs every 10 seconds (setInterval) |
| **AppState change** | Runs when app returns to `'active'` |
| **Manual** | Via `triggerSync()` (passed to ReadingScreen for post-submit sync) |

### Sync Flow (detailed)

1. **Fetch permissions**: `GET /api/key/info`. Validates API key, caches staff permissions (`can_enroll_customer`, `can_read_meters`, etc.) in local config.
2. **Fetch NFC config**: `GET /api/nfc/config`. Retrieves `nfc_pwd_secret` (offline password computation) and `nfc_generation` (cache invalidation counter). Clears local NFC cache if generation changed.
3. **Upload NFC enrollments**: unsynced enrollments from local `nfc_enrollments` → `POST /api/nfc/sync`. Mark synced on success.
4. **Upload readings**: unsynced readings (`synced=0 AND rejected=0`) → `POST /api/readings/sync`. Mark synced (with server ID) or rejected (if duplicate).
5. **Check for changes**: `GET /api/customers/changed?since=<lastSyncTime>`. Returns changed customer numbers + server timestamp.
6. **Download**: pipelined batches of up to 500 customer numbers via `GET /api/readings/bulk`. Per batch: fetch next batch in background while processing current one; upsert `nfc_cache` from `nfc_uid` fields (PWD via `computeTagPwd(nfc_pwd_secret, uid)`); call `replaceCustomerData()` per customer with individual commits; drop old readings and insert fresh data.
7. **Update timestamp**: save `server_time` as `lastSyncTime`.
8. **Cleanup**: delete synced NFC enrollment records.

### Concurrency

- `syncingRef` prevents concurrent syncs
- `AbortController` cancels the previous sync when a new one is triggered
- All DB operations serialized through `withDb()` (sequential promise queue)

### First Sync Behavior

`lastSyncTime` defaults to `0` (Unix epoch). First sync triggers a full download of all active customers and their reading history.

## Database Schema

### Tables

```sql
config (key TEXT PRIMARY KEY, value TEXT)
customers (customer_number TEXT PRIMARY KEY, ...)
readings (id INTEGER PRIMARY KEY AUTOINCREMENT, server_id INTEGER UNIQUE,
 customer_number TEXT, reading_value REAL, timestamp INTEGER,
 synced INTEGER DEFAULT 0, rejected INTEGER DEFAULT 0)
nfc_cache (uid TEXT PRIMARY KEY, customer_number TEXT, password TEXT)
nfc_enrollments (id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT,
 customer_number TEXT, synced INTEGER DEFAULT 0)
```

### Key Config Values

| Key | Type | Description |
|---|---|---|
| `serverUrl` | string | BillServer base URL |
| `apiKey` | string | API token |
| `historyCount` | int | Readings per customer (UI default 5, sync defaults to 5 if unset) |
| `lastSyncTime` | int | Server timestamp for incremental sync (default 0 = full download) |
| `nfc_pwd_secret` | string | Secret for deriving NFC tag passwords |
| `nfc_generation` | int | Generation counter for NFC secret rotation |
| `nfc_has_pending` | string | `'1'` if local NFC enrollments need upload |
| `server_time` | string | Server timestamp used for month boundary calculations |
| `pricing_tiers` | string | JSON array of pricing tiers (24h cache) |
| `pricing_fetched_at` | string | Timestamp when pricing was last fetched |
| `canEnrollCustomer` | string | Cached `can_enroll_customer` permission |
| `canReadMeters` | string | Cached `can_read_meters` permission |
| `perm_fetched` | string | `'1'` after first permission fetch |
| `lastServerWrite` | int | Timestamp of last server write operation |

## Duplicate Month Protection

Before saving a reading (locally or syncing to server), the app checks for an existing reading by the same customer in the current calendar month. The server also enforces this check independently.

## Request Flow

```mermaid
graph TD
 A[User enters reading] --> B{saveReading() in DB}
 B --> C[Local SQLite]
 B --> D{synced=0}
 D --> E[Next sync cycle picks it up]
 E --> F[POST /api/readings/sync]
 F --> G{Server validates}
 G -->|"OK"| H[markReadingSynced]
 G -->|"Duplicate"| I[markReadingRejected]
```

## Type Conversions

Sync service handles the mismatch between API types (`customer_number` as `number`) and SQLite storage (`customer_number` as `string`):

| Direction | Conversion |
|---|---|
| Uploading readings | `Number(r.customer_number)` → number |
| Uploading NFC enrollments | `Number(e.customer_number)` → number |
| Storing downloaded customers | `String(data.customer.customer_number)` → string |
| Storing NFC cache | `String(tag.customer_number)` → string |
| Inline NFC enrollment sync | `Number(accountNumber)` → number |
