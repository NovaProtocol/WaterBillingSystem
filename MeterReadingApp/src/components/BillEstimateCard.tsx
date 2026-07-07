import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

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

interface BillEstimateCardProps {
  tiers: PricingTier[];
  consumption: number;
  bill: { total: number; breakdown: BreakdownItem[] };
  showPricing: boolean;
  onToggle: () => void;
}

export default function BillEstimateCard({
  tiers,
  consumption,
  bill,
  showPricing,
  onToggle,
}: BillEstimateCardProps) {
  if (tiers.length === 0 || consumption <= 0) return null;

  return (
    <View>
      <TouchableOpacity style={styles.pricingToggle} onPress={onToggle}>
        <Text style={styles.pricingToggleText}>
          {showPricing ? 'Hide' : 'Show'} Bill Estimate
        </Text>
        <Text style={styles.pricingToggleArrow}>
          {showPricing ? '\u25B2' : '\u25BC'}
        </Text>
      </TouchableOpacity>

      {showPricing && (
        <View style={styles.pricingBox}>
          <Text style={styles.pricingTitle}>
            Estimated Bill for {consumption.toFixed(1)} m³
          </Text>
          {bill.breakdown.map((item, i) => (
            <View key={i} style={styles.pricingRow}>
              <Text
                style={[
                  styles.pricingLabel,
                  item.units === 0 && styles.pricingZero,
                ]}
              >
                {item.label}
              </Text>
              <Text
                style={[
                  styles.pricingUnits,
                  item.units === 0 && styles.pricingZero,
                ]}
              >
                {item.units.toFixed(2)} m³
              </Text>
              <Text
                style={[
                  styles.pricingCharge,
                  item.units === 0 && styles.pricingZero,
                ]}
              >
                ₱{item.charge.toFixed(2)}
              </Text>
            </View>
          ))}
          <View style={styles.pricingTotal}>
            <Text style={styles.pricingTotalLabel}>Total</Text>
            <Text style={styles.pricingTotalValue}>
              ₱{bill.total.toFixed(2)}
            </Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  pricingToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    paddingHorizontal: 14,
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#DDD',
    marginBottom: 8,
  },
  pricingToggleText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#4A90D9',
  },
  pricingToggleArrow: {
    fontSize: 12,
    color: '#999',
  },
  pricingBox: {
    backgroundColor: '#fff',
    borderRadius: 8,
    padding: 14,
    borderWidth: 1,
    borderColor: '#DDD',
    marginBottom: 12,
  },
  pricingTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 8,
  },
  pricingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 3,
  },
  pricingLabel: {
    fontSize: 12,
    color: '#333',
    flex: 1,
  },
  pricingUnits: {
    fontSize: 12,
    color: '#666',
    width: 70,
    textAlign: 'right',
  },
  pricingCharge: {
    fontSize: 12,
    fontWeight: '600',
    color: '#333',
    width: 80,
    textAlign: 'right',
  },
  pricingZero: {
    color: '#ccc',
  },
  pricingTotal: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: '#DDD',
    paddingTop: 6,
    marginTop: 4,
  },
  pricingTotalLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  pricingTotalValue: {
    fontSize: 14,
    fontWeight: '700',
    color: '#e94560',
  },
});
