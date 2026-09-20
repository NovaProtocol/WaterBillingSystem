# MeterReadingApp

React Native (Expo) mobile app for water utility field staff. Workers scan NFC tags on water meters, record readings offline, and sync with BillServer.

## Features

- **NFC scanning**: tap a tag to look up the customer and record a reading
- **Offline-first**: readings stored locally, synced when connectivity is available
- **Map view**: plot customers by GPS coordinates
- **Auto-sync**: polls BillServer every 10 seconds for changes
- **NFC enrollment**: authorized staff can enroll new NFC tags onto meters
- **QR scanning**: fallback customer lookup method

## Quick Start

```bash
npx expo start
```

Configure server URL and API key in the app's Settings screen.

## Architecture

- Local SQLite database mirrors server data
- Sync service handles bidirectional data exchange
- NFC tags use NTAG215 clones with PWD_AUTH security
