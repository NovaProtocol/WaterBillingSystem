import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { CustomerRow } from '@/db/database';

interface BreakdownItem {
  label: string;
  units: number;
  charge: number;
}

interface SubmitSummaryProps {
  submittedValue: number;
  customer: CustomerRow;
  submittedConsumption: number;
  submittedBill: { total: number; breakdown: BreakdownItem[] };
  savedOffline: boolean;
  onBackToScan: () => void;
}

export default function SubmitSummary({
  submittedValue,
  customer,
  submittedConsumption,
  submittedBill,
  savedOffline,
  onBackToScan,
}: SubmitSummaryProps) {
  return (
    <View style={styles.summaryContainer}>
      <Text style={styles.summaryIcon}>{'\u2705'}</Text>
      <Text style={styles.summaryTitle}>Reading Submitted!</Text>
      {savedOffline && (
        <Text style={styles.offlineNote}>Saved offline, will sync later</Text>
      )}

      <View style={styles.summaryCard}>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Customer</Text>
          <Text style={styles.summaryValue}>{customer.name}</Text>
        </View>
        <View style={styles.summaryRow}>
          <Text style={styles.summaryLabel}>Reading</Text>
          <Text style={styles.summaryValueBold}>
            {submittedValue.toFixed(1)} m³
          </Text>
        </View>
        {submittedConsumption > 0 && (
          <>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Consumption</Text>
              <Text style={styles.summaryValue}>
                {submittedConsumption.toFixed(1)} m³
              </Text>
            </View>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>Estimated Bill</Text>
              <Text style={styles.summaryValueBold}>
                ₱{submittedBill.total.toFixed(2)}
              </Text>
            </View>
          </>
        )}
      </View>

      <TouchableOpacity style={styles.printButton}>
        <Text style={styles.printButtonText}>{'\uD83D\uDDA8'} Print Receipt</Text>
      </TouchableOpacity>

      <TouchableOpacity style={styles.backToScanButton} onPress={onBackToScan}>
        <Text style={styles.backToScanText}>Back to Scan</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  summaryContainer: {
    alignItems: 'center',
    paddingTop: 40,
  },
  summaryIcon: {
    fontSize: 64,
    marginBottom: 12,
  },
  summaryTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 4,
  },
  offlineNote: {
    fontSize: 13,
    color: '#e94560',
    fontWeight: '600',
    marginBottom: 24,
  },
  summaryCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    width: '100%',
    marginBottom: 24,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  summaryLabel: {
    fontSize: 14,
    color: '#666',
  },
  summaryValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
  },
  summaryValueBold: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  printButton: {
    backgroundColor: '#1A1A2E',
    borderRadius: 8,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignItems: 'center',
    marginBottom: 12,
    width: '100%',
    opacity: 0.5,
  },
  printButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  backToScanButton: {
    backgroundColor: '#4A90D9',
    borderRadius: 8,
    paddingVertical: 14,
    paddingHorizontal: 32,
    alignItems: 'center',
    width: '100%',
  },
  backToScanText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
