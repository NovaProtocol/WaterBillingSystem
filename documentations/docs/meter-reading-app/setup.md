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

This starts the Metro bundler. You'll see a QR code in the terminal. Scan it with the Expo Go app (Android) or Camera app (iOS) to load the app on your device.

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

The app is configured through its **Settings screen** (gear icon on Home). No external config files are needed.

### Server URL

Enter the full URL to your BillServer instance, e.g.:

```
http://192.168.1.100:5005
```

The app will test the connection by making a HEAD request to the server root.

### API Key

Enter an API key manually or tap the QR icon to scan one:

1. Go to BillServer Staff Portal → **Meter Reading** page
2. Click **Generate API Key**
3. Copy the key (format: `CRDC-<32hex>`)
4. In the app Settings, paste the key or tap the QR icon to scan

### History Count

Configure how many past readings to display per customer (1–24). UI default: 5. If unset, the sync engine defaults to 12 when downloading readings from the server.

## Initial Sync

After setting the server URL and API key, the app:
1. Navigates to the **Home** screen
2. Automatically starts syncing customer data in the background
3. Shows a sync indicator pill at the bottom-left corner

The first sync may take a few seconds depending on the number of customers. Subsequent syncs are incremental (only changed customers are downloaded).

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
