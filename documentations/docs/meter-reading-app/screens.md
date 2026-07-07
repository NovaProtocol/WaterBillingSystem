# Screens & Components

## Navigation

The app uses a `NativeStackNavigator` with the following routes:

```typescript
type RootStackParamList = {
  Loading: undefined;
  Unauthenticated: undefined;
  Home: undefined;
  Settings: undefined;
  Reading: undefined;
  CustomerDetail: { customerNumber: string };
  Map: undefined;
  NfcEnroll: undefined;
};
```

The initial route is determined dynamically:
- If `serverUrl` and `apiKey` are configured → `'Home'`
- Otherwise → `'Unauthenticated'`

All screens have `headerShown: false` — custom headers are used throughout.

```mermaid
graph TD
    START(["App Launch"]) --> CHECK{serverUrl + apiKey set?}
    CHECK -->|"No"| UNAUTH["UnauthenticatedScreen<br/>'Open Settings'"]
    CHECK -->|"Yes"| HOME["HomeScreen"]
    HOME -->|"gear icon"| SETT["SettingsScreen"]
    HOME -->|"Start Reading"| READ["ReadingScreen"]
    HOME -->|"Map View"| MAP["MapScreen"]
    HOME -->|"customer press"| CUST["CustomerDetailScreen"]
    HOME -->|"Enroll" button| NFC["NfcEnrollScreen"]
    NFC --> HOME
    READ -->|"customer press"| CUST
    SETT -->|"save/reset"| HOME
    MAP --> HOME
    CUSTOM --> HOME
```

---

## Screens

### HomeScreen

The main dashboard showing customer counts, filters, and navigation actions.

**Components used**: `CustomerCountCard`, `CustomerFilterBar`, `UnreadListModal`, `FilterPickerModal`

Features:
- Total customer count (filtered or all)
- Unread this month count badge
- Phase / Block / Street filter chips
- "Map View" button → navigates to `Map`
- "Start Reading" button → navigates to `Reading`
- Settings gear icon → navigates to `Settings`
- **Hidden "Enroll" button** (green chip) — only visible when API key has `can_enroll_customer` permission
- Pull-to-refresh triggers sync

### NfcEnrollScreen

NFC tag enrollment screen. Only accessible to staff with `can_enroll_customer` permission.

**Phases**:
1. **`search`** — Type customer number (auto-suggest from local DB, limit 15 results)
2. **`verify`** — Shows selected customer details (name, number, address, phase/block)
3. **`programming`** — Holds phone near NFC tag, programs it with the account number
4. **`done`** — Success confirmation with option to enroll another or return home
5. **`error`** — Error display with retry option

**Programming steps**:
1. Read tag UID
2. Compute password = `computeTagPwd(nfc_pwd_secret, uid)`
3. Detect if tag is reusable (try PWD_AUTH with factory password FFFFFFFF then 00000000)
4. Write customer number ASCII (4-byte padded) to pages 7+
5. Verify customer data by reading back pages
6. Write PWD to page 133, PACK to page 134
7. Verify PWD+PACK together via PWD_AUTH (check PACK = `[00:00]`)
8. Write CFG0 `[04:00:00:04]` to page 131
9. Verify CFG0 by reading back page 131
10. Write CFG1 `[80:00:00:00]` to page 132 (activates read+write protection)
11. Verify CFG1 by reading back page 132
12. Final verification: re-authenticate with new PWD, read back customer data
13. Save to `nfc_cache` + `nfc_enrollments` locally
14. Upload to server immediately via `POST /api/nfc/sync`

### ReadingScreen

The core meter reading workflow. Accepts a customer number from NFC scan or manual entry.

**Components used**: `NfcScanner`, `CustomerInfoCard`, `ReadingHistoryPill`, `ReadingInput`, `BillEstimateCard`, `SubmitSummary`

Workflow states:
1. **`scan`** — Waiting for NFC tag or manual number entry
2. **`found`** — Customer found, showing info card, reading history, and input
3. **`submitting`** — Sending reading to local DB (and optionally to server)
4. **`submitted`** — Confirmation with `SubmitSummary`

Key behavior:
- NFC listener is active in `scan` state — uses **PWD_AUTH** to authenticate and read protected tags
- If a reading already exists for this customer in the current month, the input is disabled with a "Duplicate Month" warning
- Bill estimate recalculates as the user types
- After successful submit, shows a confirmation and offers "Back to Scan"

### CustomerDetailScreen

Displays full customer information with readings and map coordinates.

**Route params**: `{ customerNumber: string }`

Displays:
- Customer name, number, address
- Phase / Block / Street
- Contact info
- Recent readings list (value, date, reader)
- FlatList of all customers with coordinates (selected customer highlighted)

### MapScreen

Leaflet.js map rendered inside a WebView. Shows customer markers with popups.

**Components used**: None standalone (renders HTML via WebView)

Map features:
- Customer pins at (x_coordinate, y_coordinate)
- Popups showing: name, customer number, address, last reading
- Powered by Leaflet 1.9.4 with OpenStreetMap tiles

### SettingsScreen

Configuration screen for app setup.

**Components used**: `QrScanner`

Settings:
| Setting | Description |
|---|---|
| **Server URL** | BillServer base URL |
| **API Token** | API key (manual entry or QR scan) |
| **History Per Customer** | Slider (1–24), default 5 (sync defaults to 12 if unset) |
| **Clear Unsynced** | Drop readings not yet synced to server |
| **Reset All Data** | Clears DB and returns to Unauthenticated screen |

---

## Components

### NfcScanner
Invisible component that runs a continuous scan loop using `NfcTech.NfcA`. On tag discovery:
1. Reads UID hex from pages 0-1 of the tag (always public)
2. Checks if tag is MifareUltralight via `isMifareUltralight()`
3. Looks up UID in local `nfc_cache` table
4. Computes password via `computeTagPwd(nfcPwdSecret, uid)` (fallback: cached PWD → factory FFFFFFFF → factory 00000000)
5. Sends **PWD_AUTH** via `NfcManager.transceive()`, reads memory pages 7–18, parses raw ASCII to extract customer number
6. Verifies customer number matches `nfc_cache` entry (tampering detection)
7. Calls `onTag(customerNumber)` or `onError(message)`

### QrScanner
Camera view using `expo-camera` `CameraView`. Scans QR codes containing API keys. Requests camera permission on first use.

### CustomerInfoCard
Displays customer name, number, and address in a styled card.

### ReadingHistoryPill
A pill button showing the number of past readings. Tapping opens a modal with a scrollable list of readings (value, date, reader, synced/rejected status).

### ReadingInput
Numeric `TextInput` with decimal keypad. Accepts meter reading values in cubic meters (m³).

### BillEstimateCard
Toggle-able card showing the estimated bill for the entered reading. Breaks down costs by pricing tier with subtotals and total.

### SubmitSummary
Post-submit confirmation card showing: checkmark, customer name, reading value, consumption since last reading, estimated bill amount.

### CustomerCountCard
Large centered count display with "Unread This Month" button.

### CustomerFilterBar
Three filter chips (Phase / Block / Street) and a "Clear" button. Each chip opens a bottom-sheet picker.

### FilterPickerModal
Bottom-sheet modal with a FlatList of filter options. Dynamically populated from distinct values in the local customer database.

### UnreadListModal
Bottom-sheet modal listing customers with no reading in the current month. Pressing a row navigates to `CustomerDetailScreen`.

### ErrorBoundary
React class-based error boundary. Displays "Something went wrong" with error details and a "Restart" button.
