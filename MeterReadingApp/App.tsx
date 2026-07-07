import { useEffect, useState } from 'react';
import { ActivityIndicator, Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import NfcManager from 'react-native-nfc-manager';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { getConfig, getUnsyncedReadings } from '@/db/database';
import { useSync, type SyncStatus } from '@/services/syncService';
import { SyncContext } from '@/services/syncContext';
import ErrorBoundary from '@/components/ErrorBoundary';
import HomeScreen from '@/screens/HomeScreen';
import ReadingScreen from '@/screens/ReadingScreen';
import SettingsScreen from '@/screens/SettingsScreen';
import CustomerDetailScreen from '@/screens/CustomerDetailScreen';
import MapScreen from '@/screens/MapScreen';
import NfcEnrollScreen from '@/screens/NfcEnrollScreen';
import type { RootStackParamList, RootStackScreenProps } from '@/types/navigation';

const Stack = createNativeStackNavigator<RootStackParamList>();

const STATUS_CONFIG: Record<SyncStatus, { dot: string; label: string; dotColor: string; bg: string }> = {
  idle:    { dot: '\u25CB', label: 'Idle',       dotColor: '#999',   bg: '#F0F0F0' },
  syncing: { dot: '\u25D0', label: 'Syncing...', dotColor: '#F5A623', bg: '#FFF3E0' },
  synced:  { dot: '\u25CF', label: 'Synced',     dotColor: '#34A853', bg: '#E8F5E9' },
  error:   { dot: '\u25CF', label: 'Sync Error', dotColor: '#D32F2F', bg: '#FFEBEE' },
};

function LoadingScreen() {
  return (
    <View style={styles.centered}>
      <ActivityIndicator size="large" color="#4A90D9" />
    </View>
  );
}

function UnauthenticatedScreen({ navigation }: RootStackScreenProps<'Unauthenticated'>) {
  return (
    <View style={styles.centered}>
      <StatusBar style="dark" />
      <View style={styles.unauthLock}>
        <View style={styles.lockBody} />
        <View style={styles.lockShackle} />
      </View>
      <Text style={styles.unauthTitle}>Not yet authenticated</Text>
      <Text style={styles.unauthSub}>Configure your connection in settings</Text>
      <TouchableOpacity
        style={styles.settingsBtn}
        onPress={() => navigation.navigate('Settings')}
      >
        <View style={styles.settingsBtnIcon}>
          <View style={styles.gearTeeth} />
          <View style={styles.gearHole} />
        </View>
        <Text style={styles.settingsBtnText}>Open Settings</Text>
      </TouchableOpacity>
    </View>
  );
}

function ErrorScreen({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <View style={styles.centered}>
      <StatusBar style="dark" />
      <Text style={styles.unauthTitle}>Database Error</Text>
      <Text style={styles.unauthSub}>{error}</Text>
      <TouchableOpacity
        style={styles.settingsBtn}
        onPress={onRetry}
      >
        <Text style={styles.settingsBtnText}>Retry</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function App() {
  const [dbError, setDbError] = useState<string | null>(null);
  const [initialRoute, setInitialRoute] = useState<keyof RootStackParamList | null>(null);
  const [showSyncLog, setShowSyncLog] = useState(false);
  const [unsyncedCount, setUnsyncedCount] = useState(0);
  const { syncStatus, triggerSync, lastError, lastSyncCount, pendingCount, serverTotal, lastSyncTime, localCount, resyncNfc, resyncReadings, resyncing } = useSync();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    async function pollUnsynced() {
      try {
        const rows = await getUnsyncedReadings();
        setUnsyncedCount(rows.length);
      } catch {
        // db error is handled by sync's own retry
      }
    }
    pollUnsynced();
    const interval = setInterval(pollUnsynced, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    NfcManager.start();
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const [url, key] = await Promise.all([
        getConfig('serverUrl'),
        getConfig('apiKey'),
      ]);
      setInitialRoute(url && key ? 'Home' : 'Unauthenticated');
      setReady(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      console.warn('[app] checkAuth failed:', msg);
      setDbError(msg);
      setInitialRoute('Home');
      setReady(true);
    }
  }

  if (!ready) {
    return <LoadingScreen />;
  }

  if (initialRoute && dbError) {
    return <ErrorScreen error={dbError} onRetry={() => { setDbError(null); setReady(false); checkAuth(); }} />;
  }

  return (
    <View style={styles.root}>
      <ErrorBoundary>
        <SyncContext.Provider value={{ triggerSync }}>
          <NavigationContainer>
            <Stack.Navigator
              initialRouteName={initialRoute ?? 'Home'}
              screenOptions={{ headerShown: false }}
            >
              <Stack.Screen name="Unauthenticated" component={UnauthenticatedScreen} />
              <Stack.Screen name="Home" component={HomeScreen} />
              <Stack.Screen name="Settings" component={SettingsScreen} />
              <Stack.Screen name="Reading" component={ReadingScreen} />
              <Stack.Screen name="CustomerDetail" component={CustomerDetailScreen} />
              <Stack.Screen name="Map" component={MapScreen} />
              <Stack.Screen name="NfcEnroll" component={NfcEnrollScreen} />
            </Stack.Navigator>
          </NavigationContainer>
        </SyncContext.Provider>
      </ErrorBoundary>
      <SyncIndicator
        status={syncStatus}
        onPress={triggerSync}
        onLongPress={() => setShowSyncLog(true)}
        error={syncStatus === 'error' && lastError ? lastError : undefined}
      />

      <Modal
        visible={showSyncLog}
        transparent
        animationType="fade"
        onRequestClose={() => setShowSyncLog(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.syncLogModal}>
            <Text style={styles.syncLogTitle}>Sync Status</Text>
            <View style={styles.syncLogRow}>
              <Text style={styles.syncLogLabel}>Status</Text>
              <Text style={styles.syncLogValue}>{syncStatus}</Text>
            </View>
            <View style={styles.syncLogRow}>
              <Text style={styles.syncLogLabel}>Customer</Text>
              <Text style={styles.syncLogValue}>{localCount || '--'} / {serverTotal || '--'}</Text>
            </View>
            <View style={styles.syncLogRow}>
              <Text style={styles.syncLogLabel}>Last sync</Text>
              <Text style={styles.syncLogValue}>{lastSyncTime || '--'}</Text>
            </View>
            <View style={styles.syncLogRow}>
              <Text style={styles.syncLogLabel}>Pending uploads</Text>
              <Text style={styles.syncLogValue}>{unsyncedCount}</Text>
            </View>
            {lastError && (
              <View style={styles.syncLogRow}>
                <Text style={styles.syncLogLabel}>Last error</Text>
                <Text style={[styles.syncLogValue, { color: '#D32F2F', flex: 1, fontSize: 12 }]}>{lastError}</Text>
              </View>
            )}
            <TouchableOpacity
              style={styles.syncLogBtn}
              onPress={() => { triggerSync(); setShowSyncLog(false); }}
            >
              <Text style={styles.syncLogBtnText}>Sync Now</Text>
            </TouchableOpacity>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
              <TouchableOpacity
                style={[styles.syncLogBtn, { flex: 1, backgroundColor: '#E74C3C' }]}
                onPress={() => { resyncNfc(); setShowSyncLog(false); }}
                disabled={resyncing}
              >
                <Text style={styles.syncLogBtnText}>Resync NFC</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.syncLogBtn, { flex: 1, backgroundColor: '#E67E22' }]}
                onPress={() => { resyncReadings(); setShowSyncLog(false); }}
                disabled={resyncing}
              >
                <Text style={styles.syncLogBtnText}>Resync Readings</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity
              style={styles.syncLogClose}
              onPress={() => setShowSyncLog(false)}
            >
              <Text style={styles.syncLogCloseText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function SyncIndicator({ status, onPress, onLongPress, error }: { status: SyncStatus; onPress: () => void; onLongPress: () => void; error?: string }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <View style={styles.syncWrapper}>
      <TouchableOpacity style={[styles.syncBar, { backgroundColor: cfg.bg }]} onPress={onPress} onLongPress={onLongPress} activeOpacity={0.7}>
        <Text style={[styles.syncDot, { color: cfg.dotColor }]}>{cfg.dot}</Text>
        <Text style={[styles.syncLabel, { color: cfg.dotColor }]}>{cfg.label}</Text>
      </TouchableOpacity>
      {error ? (
        <Text style={styles.syncErrorText} numberOfLines={2}>{error}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  centered: {
    flex: 1,
    backgroundColor: '#F5F7FA',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  unauthLock: {
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 16,
    width: 48,
    height: 48,
  },
  lockBody: {
    width: 32,
    height: 24,
    borderRadius: 4,
    backgroundColor: '#1A1A2E',
    marginTop: 8,
  },
  lockShackle: {
    position: 'absolute',
    top: 0,
    width: 20,
    height: 18,
    borderWidth: 4,
    borderColor: '#1A1A2E',
    borderRadius: 10,
    borderBottomWidth: 0,
    backgroundColor: 'transparent',
  },
  unauthTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 4,
  },
  unauthSub: {
    fontSize: 15,
    color: '#666',
    marginBottom: 32,
    textAlign: 'center',
  },
  settingsBtn: {
    flexDirection: 'row',
    backgroundColor: '#4A90D9',
    borderRadius: 12,
    paddingVertical: 14,
    paddingHorizontal: 28,
    alignItems: 'center',
    gap: 8,
  },
  settingsBtnIcon: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  gearTeeth: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 3,
    borderColor: '#fff',
  },
  gearHole: {
    position: 'absolute',
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#4A90D9',
  },
  settingsBtnText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '600',
  },
  syncBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: 14,
    gap: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.12,
    shadowRadius: 3,
  },
  syncErrorText: {
    fontSize: 10,
    color: '#D32F2F',
    marginTop: 2,
    marginLeft: 2,
    maxWidth: 200,
  },
  syncServerText: {
    fontSize: 10,
    color: '#555',
    marginTop: 2,
    marginLeft: 2,
  },
  syncWrapper: {
    position: 'absolute',
    bottom: 100,
    left: 16,
    zIndex: 999,
    elevation: 4,
  },
  syncDot: {
    fontSize: 14,
    lineHeight: 16,
  },
  syncLabel: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  syncLogModal: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    width: '80%',
    gap: 12,
  },
  syncLogTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1A1A2E',
    textAlign: 'center',
  },
  syncLogRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  syncLogLabel: {
    fontSize: 14,
    color: '#666',
  },
  syncLogValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
  },
  syncLogBtn: {
    backgroundColor: '#4A90D9',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  syncLogBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  syncLogClose: {
    paddingVertical: 8,
    alignItems: 'center',
  },
  syncLogCloseText: {
    color: '#999',
    fontSize: 14,
  },
});
