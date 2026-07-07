import { StyleSheet, Text, View } from 'react-native';
import type { CustomerRow } from '@/db/database';

interface CustomerInfoCardProps {
  customer: CustomerRow;
}

export default function CustomerInfoCard({ customer }: CustomerInfoCardProps) {
  return (
    <View style={styles.customerCard}>
      <Text style={styles.customerName}>{customer.name}</Text>
      <Text style={styles.customerNumber}>{customer.customer_number}</Text>
      {customer.address ? (
        <Text style={styles.customerDetail}>{customer.address}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  customerCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
  },
  customerName: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  customerNumber: {
    fontSize: 14,
    color: '#4A90D9',
    fontWeight: '600',
    marginTop: 2,
  },
  customerDetail: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
  },
});
