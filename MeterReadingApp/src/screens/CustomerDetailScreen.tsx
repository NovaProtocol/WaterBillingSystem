import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {
  getCustomer,
  getCustomersWithCoordinates,
  getCustomerReadings,
  type CustomerRow,
  type ReadingRow,
} from '@/db/database';
import { useNavigation, useRoute, type RouteProp } from '@react-navigation/native';
import type { RootStackParamList } from '@/types/navigation';

export default function CustomerDetailScreen() {
  const navigation = useNavigation();
  const route = useRoute<RouteProp<RootStackParamList, 'CustomerDetail'>>();
  const customerNumber = route.params?.customerNumber ?? '';
  const [customer, setCustomer] = useState<CustomerRow | null>(null);
  const [readings, setReadings] = useState<ReadingRow[]>([]);
  const [allCustomers, setAllCustomers] = useState<CustomerRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      const [c, r, ac] = await Promise.all([
        customerNumber ? getCustomer(customerNumber) : null,
        customerNumber ? getCustomerReadings(customerNumber, 12) : Promise.resolve([]),
        getCustomersWithCoordinates(),
      ]);
      setCustomer(c);
      setReadings(r || []);
      setAllCustomers(ac);
      setLoaded(true);
    })();
  }, [customerNumber]);

  if (!loaded) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color="#4A90D9" />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Text style={styles.backText}>Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Customer Detail</Text>
        <View style={styles.backBtn} />
      </View>

      {customer && (
        <View style={styles.infoCard}>
          <Text style={styles.custName}>{customer.name}</Text>
          <Text style={styles.custNumber}>{customer.customer_number}</Text>
          {customer.address ? <Text style={styles.custDetail}>Address: {customer.address}</Text> : null}
          {customer.contact_number ? <Text style={styles.custDetail}>Contact: {customer.contact_number}</Text> : null}
          <View style={styles.tagRow}>
            {customer.phase ? <Text style={styles.tag}>Phase {customer.phase}</Text> : null}
            {customer.block ? <Text style={styles.tag}>Block {customer.block}</Text> : null}
            {customer.street ? <Text style={styles.tag}>{customer.street}</Text> : null}
          </View>
        </View>
      )}

      <View style={styles.listSection}>
        <Text style={styles.listTitle}>Customers with Coordinates ({allCustomers.length})</Text>
        <FlatList
          data={allCustomers}
          keyExtractor={(item) => item.customer_number}
          renderItem={({ item }) => (
            <View style={[styles.listRow, item.customer_number === customerNumber && styles.listRowHighlight]}>
              <Text style={styles.listName}>{item.name}</Text>
              <Text style={styles.listNumber}>{item.customer_number}</Text>
              {item.address ? <Text style={styles.listDetail}>{item.address}</Text> : null}
              {item.x_coordinate && item.y_coordinate ? (
                <Text style={styles.listCoords}>
                  {item.x_coordinate.toFixed(4)}, {item.y_coordinate.toFixed(4)}
                </Text>
              ) : null}
            </View>
          )}
          ListEmptyComponent={
            <Text style={styles.noHistory}>No customers with coordinates.</Text>
          }
        />
      </View>

      <View style={styles.historySection}>
        <Text style={styles.historyTitle}>Recent Readings</Text>
        {readings.length === 0 ? (
          <Text style={styles.noHistory}>No readings yet.</Text>
        ) : (
          readings.slice(0, 6).map((r) => (
            <View key={r.id} style={styles.historyRow}>
              <Text style={styles.historyValue}>{r.reading_value.toFixed(1)} m3</Text>
              <Text style={styles.historyDate}>
                {new Date(r.timestamp * 1000).toLocaleDateString()}
              </Text>
            </View>
          ))
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F7FA',
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
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
    borderBottomColor: '#E0E0E0',
  },
  backBtn: {
    width: 60,
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
  infoCard: {
    backgroundColor: '#fff',
    margin: 12,
    padding: 16,
    borderRadius: 12,
  },
  custName: {
    fontSize: 20,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  custNumber: {
    fontSize: 13,
    color: '#999',
    marginTop: 2,
  },
  custDetail: {
    fontSize: 14,
    color: '#555',
    marginTop: 6,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tag: {
    backgroundColor: '#E8ECF0',
    borderRadius: 12,
    paddingVertical: 4,
    paddingHorizontal: 10,
    fontSize: 11,
    color: '#555',
    fontWeight: '500',
  },
  listSection: {
    flex: 1,
    margin: 12,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
  },
  listTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 10,
  },
  listRow: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  listRowHighlight: {
    backgroundColor: '#FFF5F7',
    borderRadius: 8,
    paddingHorizontal: 8,
    marginHorizontal: -8,
  },
  listName: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
  },
  listNumber: {
    fontSize: 12,
    color: '#999',
    marginTop: 1,
  },
  listDetail: {
    fontSize: 13,
    color: '#555',
    marginTop: 4,
  },
  listCoords: {
    fontSize: 11,
    color: '#aaa',
    marginTop: 2,
    fontFamily: 'monospace',
  },
  historySection: {
    flex: 1,
    margin: 12,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
  },
  historyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#1A1A2E',
    marginBottom: 12,
  },
  noHistory: {
    fontSize: 14,
    color: '#999',
  },
  historyRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  historyValue: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  historyDate: {
    fontSize: 12,
    color: '#999',
  },
});
