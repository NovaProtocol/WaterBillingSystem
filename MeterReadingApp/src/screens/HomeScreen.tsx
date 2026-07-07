import { useCallback, useEffect, useState } from 'react';
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '@/types/navigation';
import { BUILD_TIMESTAMP } from '@/buildTime';
import {
  getUnreadThisMonth,
  getUnreadThisMonthCount,
  getFilteredCustomerCount,
  getDistinctPhases,
  getDistinctBlocks,
  getDistinctStreets,
  getConfig,
  type CustomerRow,
  type CustomerFilters,
} from '@/db/database';
import CustomerFilterBar, { type FilterField } from '@/components/CustomerFilterBar';
import CustomerCountCard from '@/components/CustomerCountCard';
import UnreadListModal from '@/components/UnreadListModal';
import FilterPickerModal from '@/components/FilterPickerModal';

export default function HomeScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const [customerCount, setCustomerCount] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [showUnread, setShowUnread] = useState(false);
  const [unreadList, setUnreadList] = useState<CustomerRow[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const [filters, setFilters] = useState<CustomerFilters>({});
  const [phases, setPhases] = useState<string[]>([]);
  const [blocks, setBlocks] = useState<string[]>([]);
  const [streets, setStreets] = useState<string[]>([]);
  const [showFilterPicker, setShowFilterPicker] = useState<FilterField | null>(null);
  const [canEnroll, setCanEnroll] = useState(false);

  async function refreshCounts() {
    const [cc, uc] = await Promise.all([
      getFilteredCustomerCount(filters),
      getUnreadThisMonthCount(),
    ]);
    setCustomerCount(cc);
    setUnreadCount(uc);
  }

  async function refreshDropdowns() {
    const [p, b, s] = await Promise.all([
      getDistinctPhases(),
      getDistinctBlocks(),
      getDistinctStreets(),
    ]);
    setPhases(p);
    setBlocks(b);
    setStreets(s);
  }

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([refreshCounts(), refreshDropdowns()]);
    setRefreshing(false);
  }, [filters]);

  useEffect(() => {
    onRefresh();
    (async () => {
      const enrollPerm = await getConfig('canEnrollCustomer');
      setCanEnroll(enrollPerm === '1');
    })();
  }, []);

  useEffect(() => {
    const timer = setTimeout(refreshCounts, 300);
    return () => clearTimeout(timer);
  }, [filters]);

  async function openUnread() {
    const list = await getUnreadThisMonth();
    setUnreadList(list);
    setShowUnread(true);
  }

  function selectFilter(field: FilterField, value: string | null) {
    const next = { ...filters };
    if (value) {
      next[field] = value;
    } else {
      delete next[field];
    }
    setFilters(next);
    setShowFilterPicker(null);
  }

  function clearFilters() {
    setFilters({});
  }

  const hasFilters = !!(filters.phase || filters.block || filters.street);

  function activePickerField(): FilterField {
    return showFilterPicker || 'phase';
  }

  function filterOptions(field: FilterField): string[] {
    switch (field) {
      case 'phase': return phases;
      case 'block': return blocks;
      case 'street': return streets;
    }
  }

  return (
    <View style={styles.container}>
      <TouchableOpacity style={styles.gearButton} onPress={() => navigation.navigate('Settings')}>
        <Text style={styles.gearIcon}>{'\u2699'}</Text>
      </TouchableOpacity>

      {canEnroll && (
        <TouchableOpacity style={styles.enrollButton} onPress={() => navigation.navigate('NfcEnroll')}>
          <Text style={styles.enrollIcon}>{'\uD83D\uDCF6'}</Text>
          <Text style={styles.enrollText}>Enroll</Text>
        </TouchableOpacity>
      )}

      <View style={styles.headerSection}>
        <View style={styles.headerAccent} />
        <Text style={styles.title}>Meter Reader</Text>
        <Text style={styles.subtitle}>Cotta Realty Water Utility</Text>
      </View>

      <ScrollView
        style={styles.scrollArea}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} colors={['#e94560']} tintColor="#e94560" />
        }
      >
        <CustomerCountCard
          customerCount={customerCount}
          unreadCount={unreadCount}
          hasFilters={hasFilters}
          onViewUnread={openUnread}
        />

        <CustomerFilterBar
          filters={filters}
          phases={phases}
          blocks={blocks}
          streets={streets}
          onSelectFilter={setShowFilterPicker}
          onClearFilters={clearFilters}
        />
      </ScrollView>

      <View style={styles.bottom}>
        <View style={styles.bottomRow}>
          <TouchableOpacity style={styles.mapButton} onPress={() => navigation.navigate('Map')}>
            <Text style={styles.mapButtonIcon}>{'\u{1F5FA}\uFE0F'}</Text>
            <Text style={styles.mapButtonText}>Map View</Text>
          </TouchableOpacity>
          <View style={styles.bottomDivider} />
          <TouchableOpacity style={styles.readButton} onPress={() => navigation.navigate('Reading')}>
            <Text style={styles.readButtonIcon}>{'\u{1F4F1}'}</Text>
            <Text style={styles.readButtonText}>Start Reading</Text>
          </TouchableOpacity>
        </View>
      </View>

      <Text style={styles.buildTime}>
        Build {new Date(BUILD_TIMESTAMP).toLocaleDateString()}{' '}
        {new Date(BUILD_TIMESTAMP).toLocaleTimeString()}
      </Text>

      <UnreadListModal
        visible={showUnread}
        unreadList={unreadList}
        onClose={() => setShowUnread(false)}
        onSelectCustomer={(num) => navigation.navigate('CustomerDetail', { customerNumber: num })}
      />

      <FilterPickerModal
        visible={showFilterPicker !== null}
        title={showFilterPicker ? FILTER_LABELS[showFilterPicker] : ''}
        options={filterOptions(activePickerField())}
        selected={showFilterPicker ? filters[showFilterPicker] : undefined}
        onSelect={(value) => showFilterPicker && selectFilter(showFilterPicker, value)}
        onClose={() => setShowFilterPicker(null)}
      />
    </View>
  );
}

const FILTER_LABELS: Record<FilterField, string> = {
  phase: 'Phase',
  block: 'Block',
  street: 'Street',
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F0F2F5',
  },
  gearButton: {
    position: 'absolute',
    top: 60,
    right: 20,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.06)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  gearIcon: {
    fontSize: 22,
    color: '#555',
  },
  enrollButton: {
    position: 'absolute',
    top: 108,
    right: 20,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: '#34A853',
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 4,
    zIndex: 10,
  },
  enrollIcon: {
    fontSize: 14,
  },
  enrollText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#fff',
  },
  headerSection: {
    backgroundColor: '#1a1a2e',
    paddingTop: 80,
    paddingBottom: 24,
    paddingHorizontal: 24,
    borderBottomLeftRadius: 24,
    borderBottomRightRadius: 24,
    position: 'relative',
    overflow: 'hidden',
  },
  headerAccent: {
    position: 'absolute',
    top: -40,
    right: -40,
    width: 160,
    height: 160,
    borderRadius: 80,
    backgroundColor: 'rgba(233,69,96,0.15)',
  },
  title: {
    fontSize: 26,
    fontWeight: '800',
    color: '#fff',
    letterSpacing: 0.5,
  },
  subtitle: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.6)',
    marginTop: 4,
    letterSpacing: 0.3,
  },
  scrollArea: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: 8,
  },
  bottom: {
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#E8ECF0',
    paddingTop: 12,
    paddingBottom: 32,
    paddingHorizontal: 20,
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  bottomDivider: {
    width: 1,
    height: 40,
    backgroundColor: '#E8ECF0',
    marginHorizontal: 4,
  },
  readButton: {
    flex: 1,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#e94560',
  },
  readButtonIcon: {
    fontSize: 20,
    marginBottom: 2,
  },
  readButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
  },
  mapButton: {
    flex: 1,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
  },
  mapButtonIcon: {
    fontSize: 20,
    marginBottom: 2,
  },
  mapButtonText: {
    color: '#555',
    fontSize: 15,
    fontWeight: '600',
  },
  buildTime: {
    fontSize: 10,
    color: '#ccc',
    textAlign: 'center',
    paddingVertical: 6,
    backgroundColor: '#fff',
  },
});
