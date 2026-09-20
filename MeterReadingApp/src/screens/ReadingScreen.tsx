import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import {
  getConfig,
  setConfig,
  getCustomer,
  getCustomerReadings,
  getReadingThisMonth,
  saveReading,
  getHistoryCount,
  type CustomerRow,
  type ReadingRow,
} from '@/db/database';
import NfcScanner from '@/components/NfcScanner';
import CustomerInfoCard from '@/components/CustomerInfoCard';
import ReadingHistoryPill from '@/components/ReadingHistoryPill';
import ReadingInput from '@/components/ReadingInput';
import BillEstimateCard from '@/components/BillEstimateCard';
import SubmitSummary from '@/components/SubmitSummary';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/types/navigation';
import { useSyncTrigger } from '@/services/syncContext';

interface PricingTier {
  label: string;
  from_unit: number;
  to_unit: number;
  rate: number;
  unit?: string;
}

interface BreakdownItem {
  label: string;
  units: number;
  charge: number;
}

interface Props {}

type ScanState = 'waiting' | 'found' | 'summary' | 'error';

export default function ReadingScreen({}: Props) {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { triggerSync } = useSyncTrigger();
  const [scanState, setScanState] = useState<ScanState>('waiting');
  const [customer, setCustomer] = useState<CustomerRow | null>(null);
  const [allReadings, setAllReadings] = useState<ReadingRow[]>([]);
  const [currentReading, setCurrentReading] = useState('');
  const [submittedValue, setSubmittedValue] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [duplicateWarning, setDuplicateWarning] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [savedOffline, setSavedOffline] = useState(false);
  const [manualEntry, setManualEntry] = useState(false);
  const [manualNumber, setManualNumber] = useState('');

  const [pricingTiers, setPricingTiers] = useState<PricingTier[]>([]);
  const [showPricing, setShowPricing] = useState(false);
  const [pricingError, setPricingError] = useState(false);

  useEffect(() => {
    (async () => {
      const cached = await getConfig('pricing_tiers');
      const fetchedAt = await getConfig('pricing_fetched_at');
      if (cached && fetchedAt) {
        const age = Date.now() - parseInt(fetchedAt, 10);
        if (age < 24 * 60 * 60 * 1000) {
          try { setPricingTiers(JSON.parse(cached)); return; } catch {}
        }
      }
      const serverUrl = await getConfig('serverUrl');
      const apiKey = await getConfig('apiKey');
      if (!serverUrl || !apiKey) return;
      try {
        const res = await fetch(`${serverUrl}/api/pricing`, {
          headers: { Authorization: `Bearer ${apiKey}` },
        });
        if (res.ok) {
          const data = await res.json();
          const tiers = data.tiers ?? [];
          setPricingTiers(tiers);
          await setConfig('pricing_tiers', JSON.stringify(tiers));
          await setConfig('pricing_fetched_at', String(Date.now()));
        }
      } catch {
        setPricingError(true);
      }
    })();
  }, []);

  async function handleTag(customerNumber: string) {
    const cust = await getCustomer(customerNumber);
    if (!cust) {
      setErrorMsg(
        `Customer "${customerNumber}" not found in local database. Sync first.`
      );
      setScanState('error');
      return;
    }

    const limit = await getHistoryCount();
    const readings = await getCustomerReadings(customerNumber, limit);

    const existing = await getReadingThisMonth(customerNumber);
    if (existing) {
      const by = existing.reader_id ? ` by ${existing.reader_id}` : '';
      setDuplicateWarning(
        `This meter has already been read${by} this month. Contact technical support if this is unexpected.`
      );
    } else {
      setDuplicateWarning(null);
    }

    setCustomer(cust);
    setAllReadings(readings);
    setCurrentReading('');
    setErrorMsg('');
    setScanState('found');
  }

  async function handleSubmit() {
    if (!customer || submitting) return;
    const val = parseFloat(currentReading);
    if (isNaN(val) || val < 0) return;

    setSubmitting(true);
    setSavedOffline(false);
    try {
      const serverUrl = await getConfig('serverUrl');
      const apiKey = await getConfig('apiKey');
      const online = await checkServerReachable(serverUrl, apiKey);
      await saveReading(customer.customer_number, val);
      if (!online) {
        setSavedOffline(true);
      }
      setSubmittedValue(val);
      setCurrentReading('');
      setScanState('summary');
      triggerSync();
    } catch (e) {
      Alert.alert('Error', e instanceof Error ? e.message : 'Failed to save reading');
    } finally {
      setSubmitting(false);
    }
  }

  function handleBackToScan() {
    setCustomer(null);
    setAllReadings([]);
    setCurrentReading('');
    setSubmittedValue(0);
    setErrorMsg('');
    setManualEntry(false);
    setManualNumber('');
    setScanState('waiting');
  }

  async function handleManualLookup() {
    const num = manualNumber.trim().toUpperCase();
    if (!num) return;
    const cust = await getCustomer(num);
    if (!cust) {
      Alert.alert('Not Found', `Customer "${num}" not found.`);
      return;
    }
    setCustomer(cust);

    const existing = await getReadingThisMonth(num);
    if (existing) {
      const by = existing.reader_id ? ` by ${existing.reader_id}` : '';
      setDuplicateWarning(
        `This meter has already been read${by} this month. Contact technical support if this is unexpected.`
      );
    } else {
      setDuplicateWarning(null);
    }

    const limit = await getHistoryCount();
    const readings = await getCustomerReadings(num, limit);
    setAllReadings(readings);
    setScanState('found');
  }

  const lastReading = allReadings.length > 0 ? allReadings[0].reading_value : 0;
  const entered = parseFloat(currentReading) || 0;
  const consumption = entered > lastReading ? entered - lastReading : 0;
  const billEstimate = computeBill(consumption, pricingTiers);
  const submittedConsumption =
    submittedValue > lastReading ? submittedValue - lastReading : 0;
  const submittedBill = computeBill(submittedConsumption, pricingTiers);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity
          onPress={scanState === 'summary' ? handleBackToScan : () => navigation.goBack()}
          style={styles.backButton}
        >
          <Text style={styles.backText}>{'\u2190'} Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>
          {scanState === 'summary' ? 'Reading Complete' : duplicateWarning ? 'Duplicate, Already Read' : 'Meter Reading'}
        </Text>
        <View style={styles.backButton} />
      </View>

      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {scanState === 'waiting' && (
          <View style={styles.awaitingContainer}>
            <Text style={styles.awaitingIcon}>{'\uD83D\uDCF6'}</Text>
            <Text style={styles.awaitingText}>Awaiting NFC</Text>
            <Text style={styles.awaitingHint}>
              Tap your phone to an NFC-enabled meter
            </Text>
            {!manualEntry ? (
              <TouchableOpacity
                style={styles.manualButton}
                onPress={() => setManualEntry(true)}
              >
                <Text style={styles.manualButtonText}>Manual Entry</Text>
              </TouchableOpacity>
            ) : (
              <View style={styles.manualContainer}>
                <TextInput
                  style={styles.manualInput}
                  placeholder="Enter customer number"
                  placeholderTextColor="#999"
                  value={manualNumber}
                  onChangeText={setManualNumber}
                  autoCapitalize="characters"
                  autoFocus
                />
                <TouchableOpacity
                  style={styles.manualSubmit}
                  onPress={handleManualLookup}
                >
                  <Text style={styles.manualSubmitText}>Look Up</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  onPress={() => setManualEntry(false)}
                >
                  <Text style={styles.manualCancel}>Cancel</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}

        {scanState === 'found' && customer && (
          <View>
            {duplicateWarning && (
              <View style={styles.duplicateBanner}>
                <Text style={styles.duplicateIcon}>{'\u26A0\uFE0F'}</Text>
                <Text style={styles.duplicateText}>{duplicateWarning}</Text>
              </View>
            )}

            <CustomerInfoCard customer={customer} />

            <ReadingHistoryPill readings={allReadings} />

            <ReadingInput
              value={currentReading}
              onChangeText={setCurrentReading}
              disabled={submitting}
            />

            {pricingError && (
              <View style={styles.pricingWarning}>
                <Text style={styles.pricingWarningText}>
                  Could not load pricing data. Bill estimate may be unavailable.
                </Text>
              </View>
            )}

            <BillEstimateCard
              tiers={pricingTiers}
              consumption={consumption}
              bill={billEstimate}
              showPricing={showPricing}
              onToggle={() => setShowPricing(!showPricing)}
            />

            <TouchableOpacity style={styles.printLastBtn} activeOpacity={0.7}>
              <Text style={styles.printLastBtnText}>
                {'\uD83D\uDDA8'} Print Last Receipt
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.submitButton,
                (submitting || duplicateWarning) && styles.submitButtonDisabled,
                !currentReading && styles.submitButtonDisabled,
              ]}
              onPress={handleSubmit}
              disabled={!currentReading || submitting || !!duplicateWarning}
            >
              {submitting ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : duplicateWarning ? (
                <Text style={styles.submitButtonText}>Already Read, Submit Blocked</Text>
              ) : (
                <Text style={styles.submitButtonText}>Submit Reading</Text>
              )}
            </TouchableOpacity>
          </View>
        )}

        {scanState === 'summary' && customer && (
          <SubmitSummary
            submittedValue={submittedValue}
            customer={customer}
            submittedConsumption={submittedConsumption}
            submittedBill={submittedBill}
            savedOffline={savedOffline}
            onBackToScan={handleBackToScan}
          />
        )}

        {scanState === 'error' && (
          <View style={styles.errorContainer}>
            <Text style={styles.errorIcon}>{'\u26A0\uFE0F'}</Text>
            <Text style={styles.errorText}>{errorMsg}</Text>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={() => {
                setScanState('waiting');
                setErrorMsg('');
              }}
            >
              <Text style={styles.retryText}>Try Again</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      <NfcScanner
        onTag={handleTag}
        onError={(msg) => {
          setErrorMsg(msg);
          setScanState('error');
        }}
      />
    </View>
  );
}

async function checkServerReachable(serverUrl: string | null, _apiKey: string | null): Promise<boolean> {
  if (!serverUrl) return false;
  try {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), 5000);
    const res = await fetch(`${serverUrl}/api/pricing`, {
      method: 'HEAD',
      signal: controller.signal,
    });
    clearTimeout(id);
    return res.ok;
  } catch {
    return false;
  }
}

function computeBill(
  consumption: number,
  tiers: PricingTier[]
): { total: number; breakdown: BreakdownItem[] } {
  let total = 0;
  const breakdown: BreakdownItem[] = [];
  for (const tier of tiers) {
    const unitsInTier =
      consumption <= tier.from_unit
        ? 0
        : Math.min(consumption, tier.to_unit) - tier.from_unit;
    const charge =
      tier.unit === 'flat' ? (unitsInTier > 0 ? tier.rate : 0) : unitsInTier * tier.rate;
    breakdown.push({ label: tier.label, units: unitsInTier, charge });
    total += charge;
  }
  return { total, breakdown };
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 60,
    paddingBottom: 12,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#E8ECF0',
  },
  backButton: {
    width: 70,
  },
  backText: {
    fontSize: 16,
    color: '#4A90D9',
    fontWeight: '600',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 40,
  },
  awaitingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  awaitingIcon: {
    fontSize: 64,
    marginBottom: 16,
  },
  awaitingText: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 8,
  },
  awaitingHint: {
    fontSize: 15,
    color: '#999',
    textAlign: 'center',
    marginBottom: 24,
  },
  manualButton: {
    backgroundColor: '#e94560',
    paddingVertical: 12,
    paddingHorizontal: 32,
    borderRadius: 50,
  },
  manualButtonText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 15,
  },
  manualContainer: {
    width: '100%',
    alignItems: 'center',
    gap: 12,
  },
  manualInput: {
    width: '80%',
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 10,
    padding: 12,
    fontSize: 16,
    textAlign: 'center',
    letterSpacing: 2,
    fontFamily: 'monospace',
  },
  manualSubmit: {
    backgroundColor: '#1a1a2e',
    paddingVertical: 12,
    paddingHorizontal: 40,
    borderRadius: 50,
  },
  manualSubmitText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 15,
  },
  manualCancel: {
    color: '#999',
    fontSize: 14,
    marginTop: 4,
  },
  duplicateBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF3E0',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#F5A623',
    padding: 12,
    marginBottom: 16,
    gap: 8,
  },
  duplicateIcon: {
    fontSize: 20,
  },
  duplicateText: {
    flex: 1,
    fontSize: 13,
    color: '#8D6E00',
    lineHeight: 18,
  },
  pricingWarning: {
    backgroundColor: '#FFF3E0',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#F5A623',
    padding: 10,
    marginBottom: 8,
  },
  pricingWarningText: {
    fontSize: 12,
    color: '#8D6E00',
    textAlign: 'center',
  },
  printLastBtn: {
    paddingVertical: 10,
    alignItems: 'center',
    marginBottom: 8,
    opacity: 0.5,
  },
  printLastBtnText: {
    fontSize: 13,
    color: '#666',
    fontWeight: '600',
  },
  submitButton: {
    backgroundColor: '#34A853',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 4,
  },
  submitButtonDisabled: {
    backgroundColor: '#B0B0B0',
    opacity: 0.7,
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  errorContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingTop: 100,
  },
  errorIcon: {
    fontSize: 48,
    marginBottom: 12,
  },
  errorText: {
    fontSize: 16,
    color: '#D32F2F',
    textAlign: 'center',
    marginBottom: 20,
  },
  retryButton: {
    backgroundColor: '#4A90D9',
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 32,
  },
  retryText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
