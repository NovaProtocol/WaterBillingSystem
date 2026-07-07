import { useEffect, useState } from 'react';
import {
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
  Modal,
} from 'react-native';
import { getConfig, setConfig, getHistoryCount, setHistoryCount, deleteUnsyncedReadings, deleteAllData, getUnsyncedReadings } from '@/db/database';
import QrScanner from '@/components/QrScanner';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/types/navigation';

export default function SettingsScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [serverIp, setServerIp] = useState('');
  const [serverPort, setServerPort] = useState('5005');
  const [apiToken, setApiToken] = useState('');
  const [historyCount, setHistoryCountState] = useState('5');
  const [showQrScanner, setShowQrScanner] = useState(false);
  const [scannerKey, setScannerKey] = useState(0);
  const [clearing, setClearing] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetting, setResetting] = useState(false);
  useEffect(() => {
    (async () => {
      const [url, key, hc] = await Promise.all([
        getConfig('serverUrl'),
        getConfig('apiKey'),
        getHistoryCount(),
      ]);
      if (url) {
        const match = url.match(/^https?:\/\/([^:/]+)(?::(\d+))?/);
        if (match) {
          setServerIp(match[1]);
          if (match[2]) setServerPort(match[2]);
        }
      }
      if (key) setApiToken(key);
      setHistoryCountState(String(hc));
    })();
  }, []);

  async function handleComplete() {
    if (!serverIp.trim() || !apiToken.trim()) return;
    const port = serverPort.trim() || '5005';
    await setConfig('serverUrl', `https://${serverIp.trim()}:${port}`);
    await setConfig('apiKey', apiToken.trim());
    const hc = parseInt(historyCount, 10);
    if (!isNaN(hc) && hc >= 1 && hc <= 24) {
      await setHistoryCount(hc);
    }
    navigation.reset({ index: 0, routes: [{ name: 'Home' }] });
  }

  async function handleClearUnsynced() {
    const count = (await getUnsyncedReadings()).length;
    if (count === 0) return;
    Alert.alert(
      'Clear Unsynced Readings',
      `This will delete ${count} unsynced reading(s). This cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: async () => {
          setClearing(true);
          await deleteUnsyncedReadings();
          setClearing(false);
        }},
      ]
    );
  }

  async function handleResetAll() {
    setResetting(true);
    try {
      await deleteAllData();
    } catch (e) {
      console.warn('[settings] reset failed:', e);
    }
    setResetting(false);
    setShowResetConfirm(false);
    navigation.reset({ index: 0, routes: [{ name: 'Home' }] });
  }

  function handleBarCodeScanned(data: string) {
    setApiToken(data);
    setShowQrScanner(false);
    setScannerKey(k => k + 1);
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Settings</Text>

      <Text style={styles.label}>Server IP</Text>
      <TextInput
        style={styles.textInput}
        placeholder="192.168.18.52"
        placeholderTextColor="#999"
        value={serverIp}
        onChangeText={setServerIp}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="default"
      />

      <Text style={styles.label}>Server Port</Text>
      <TextInput
        style={styles.textInput}
        placeholder="5005"
        placeholderTextColor="#999"
        value={serverPort}
        onChangeText={(v) => {
          const cleaned = v.replace(/[^0-9]/g, '');
          if (cleaned === '' || (parseInt(cleaned, 10) >= 1 && parseInt(cleaned, 10) <= 65535)) {
            setServerPort(cleaned);
          }
        }}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="number-pad"
        maxLength={5}
      />

      <Text style={styles.label}>API Token</Text>
      <View style={styles.tokenRow}>
        <TextInput
          style={[styles.textInput, styles.tokenInput]}
          placeholder="CRDC-..."
          placeholderTextColor="#999"
          value={apiToken}
          onChangeText={setApiToken}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
        />
        <TouchableOpacity
          style={styles.cameraIconBtn}
          onPress={() => setShowQrScanner(true)}
        >
          <Text style={styles.cameraIcon}>{'\uD83D\uDCF7'}</Text>
        </TouchableOpacity>
      </View>

      <Text style={styles.label}>History Per Customer</Text>
      <TextInput
        style={styles.textInput}
        placeholder="5"
        placeholderTextColor="#999"
        value={historyCount}
        onChangeText={(v) => {
          const cleaned = v.replace(/[^0-9]/g, '');
          if (cleaned === '' || (parseInt(cleaned, 10) >= 1 && parseInt(cleaned, 10) <= 24)) {
            setHistoryCountState(cleaned);
          }
        }}
        keyboardType="number-pad"
        maxLength={2}
      />
      <Text style={styles.hint}>Number of past readings shown (1–24)</Text>

      <TouchableOpacity
        style={styles.clearButton}
        onPress={handleClearUnsynced}
        disabled={clearing}
      >
        <Text style={styles.clearButtonText}>
          {clearing ? 'Clearing...' : 'Clear unsynced readings'}
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={styles.resetButton}
        onPress={() => setShowResetConfirm(true)}
      >
        <Text style={styles.resetButtonText}>Reset all data</Text>
      </TouchableOpacity>

      <Modal
        visible={showResetConfirm}
        transparent
        animationType="fade"
        onRequestClose={() => setShowResetConfirm(false)}
      >
        <View style={styles.qrOverlay}>
          <View style={styles.qrContainer}>
            <Text style={styles.modalTitle}>Reset all data?</Text>
            <Text style={styles.modalText}>
              This will delete all local customers, readings, and settings. Your configuration will be lost. You will need to reconfigure the app from scratch.
            </Text>
            <View style={styles.resetBtnRow}>
              <TouchableOpacity
                style={styles.resetCancelBtn}
                onPress={() => setShowResetConfirm(false)}
              >
                <Text style={styles.resetCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.resetConfirmBtn}
                onPress={handleResetAll}
                disabled={resetting}
              >
                <Text style={styles.resetConfirmText}>
                  {resetting ? 'Resetting...' : 'Reset'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      <TouchableOpacity style={styles.completeButton} onPress={handleComplete}>
        <Text style={styles.completeButtonText}>Complete Settings</Text>
      </TouchableOpacity>

      <Modal
        visible={showQrScanner}
        transparent
        animationType="fade"
        onRequestClose={() => setShowQrScanner(false)}
      >
        <View style={styles.qrOverlay}>
          <View style={styles.qrContainer}>
            <QrScanner
              scannerKey={scannerKey}
              onBarcodeScanned={handleBarCodeScanned}
              active={showQrScanner}
            />
            <TouchableOpacity
              style={styles.qrCloseButton}
              onPress={() => setShowQrScanner(false)}
            >
              <Text style={styles.qrCloseText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
    paddingHorizontal: 24,
    paddingTop: 80,
  },
  title: {
    fontSize: 28,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 32,
    textAlign: 'center',
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 6,
    marginTop: 16,
  },
  textInput: {
    width: '100%',
    borderWidth: 1,
    borderColor: '#DDD',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#333',
    backgroundColor: '#FAFAFA',
  },
  tokenRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tokenInput: {
    flex: 1,
  },
  cameraIconBtn: {
    width: 44,
    height: 44,
    borderRadius: 8,
    backgroundColor: '#E8ECF0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cameraIcon: {
    fontSize: 22,
  },
  clearButton: {
    backgroundColor: '#E74C3C',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 24,
  },
  clearButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  resetButton: {
    backgroundColor: '#C0392B',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 8,
  },
  resetButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1A1A2E',
    textAlign: 'center',
  },
  modalText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    lineHeight: 20,
  },
  resetBtnRow: {
    flexDirection: 'row',
    gap: 12,
    width: '100%',
  },
  resetCancelBtn: {
    flex: 1,
    backgroundColor: '#E8ECF0',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
  },
  resetCancelText: {
    color: '#333',
    fontSize: 15,
    fontWeight: '600',
  },
  resetConfirmBtn: {
    flex: 1,
    backgroundColor: '#C0392B',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
  },
  resetConfirmText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  completeButton: {
    backgroundColor: '#4A90D9',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 16,
  },
  completeButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  hint: {
    fontSize: 12,
    color: '#999',
    marginTop: 4,
  },
  qrOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  qrContainer: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    width: '85%',
    alignItems: 'center',
    gap: 16,
  },
  qrCloseButton: {
    paddingVertical: 8,
    paddingHorizontal: 24,
  },
  qrCloseText: {
    color: '#4A90D9',
    fontSize: 15,
    fontWeight: '600',
  },
});
