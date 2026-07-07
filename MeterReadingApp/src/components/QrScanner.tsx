import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';

interface QrScannerProps {
  scannerKey: number;
  onBarcodeScanned: (data: string) => void;
  active: boolean;
}

export default function QrScanner({ scannerKey, onBarcodeScanned, active }: QrScannerProps) {
  const [permission, requestPermission] = useCameraPermissions();

  if (!active) return null;

  if (!permission?.granted) {
    return (
      <View style={styles.qrPermissions}>
        <Text style={styles.qrText}>Camera permission is required to scan QR codes.</Text>
        <TouchableOpacity style={styles.submitButton} onPress={requestPermission}>
          <Text style={styles.submitText}>Grant Permission</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <>
      <CameraView
        key={scannerKey}
        style={styles.cameraPreview}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
        onBarcodeScanned={(result) => onBarcodeScanned(result.data)}
      />
      <Text style={styles.qrHint}>Scan a QR code containing the API token</Text>
    </>
  );
}

const styles = StyleSheet.create({
  qrPermissions: {
    alignItems: 'center',
    gap: 16,
    paddingVertical: 20,
  },
  qrText: {
    fontSize: 15,
    color: '#666',
    textAlign: 'center',
  },
  cameraPreview: {
    width: '100%',
    height: 280,
    borderRadius: 12,
    overflow: 'hidden',
  },
  qrHint: {
    fontSize: 13,
    color: '#999',
    textAlign: 'center',
  },
  submitButton: {
    backgroundColor: '#4A90D9',
    borderRadius: 8,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignItems: 'center',
  },
  submitText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
