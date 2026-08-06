# Setup

## Prerequisites

- Node.js >= 18
- Expo CLI (`npx expo`)
- Expo Go app on your phone (for development)
- Or: Android Studio / Xcode for emulator

## Installation

```bash
cd MeterReadingApp
npm install
```

## Development

```bash
npx expo start
```

Starts the Metro bundler. Scan the QR with the Expo Go app (Android) or Camera app (iOS) to load the app.

### Platform-Specific

```bash
# Android emulator
npx expo start --android

# iOS simulator (macOS only)
npx expo start --ios

# Web
npx expo start --web
```

## Configuration

Configured through the **Settings screen** (gear icon on Home). No external config files.

### Server URL

Enter the full URL to your BillServer instance, e.g.:

```
http://192.168.1.100:5005
```

The app tests the connection with a HEAD request to the server root.

### API Key

Enter an API key manually or tap the QR icon to scan one:

1. Go to BillServer Staff Portal → **Meter Reading** page
2. Click **Generate API Key**
3. Copy the key (format: `CRDC-<32hex>`)
4. In the app Settings, paste the key or tap the QR icon to scan

### History Count

How many past readings to display per customer (1–24). Default: 5.

## Initial Sync

After setting the server URL and API key:
1. Navigates to the **Home** screen
2. Starts syncing customer data automatically
3. Sync indicator pill at the bottom-left corner

First sync may take a few seconds depending on customer count. Subsequent syncs are incremental (only changed customers).

## Type Checking

```bash
npx tsc --noEmit
```

## Testing

```bash
npx jest
```

## EAS Build (Production)

```bash
npx eas build --platform android
npx eas build --platform ios
```

Configured in `eas.json` at the project root.
