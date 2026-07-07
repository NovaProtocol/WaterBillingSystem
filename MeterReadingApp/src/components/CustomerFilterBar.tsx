import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { CustomerFilters } from '@/db/database';

export type FilterField = 'phase' | 'block' | 'street';

const FILTER_LABELS: Record<FilterField, string> = {
  phase: 'Phase',
  block: 'Block',
  street: 'Street',
};

interface CustomerFilterBarProps {
  filters: CustomerFilters;
  phases: string[];
  blocks: string[];
  streets: string[];
  onSelectFilter: (field: FilterField) => void;
  onClearFilters: () => void;
}

export default function CustomerFilterBar({
  filters,
  phases,
  blocks,
  streets,
  onSelectFilter,
  onClearFilters,
}: CustomerFilterBarProps) {
  const hasFilters = !!(filters.phase || filters.block || filters.street);

  function activeFilterLabel(field: FilterField): string {
    const val = filters[field];
    return val || `All ${FILTER_LABELS[field]}`;
  }

  function filterOptions(field: FilterField): string[] {
    switch (field) {
      case 'phase': return phases;
      case 'block': return blocks;
      case 'street': return streets;
    }
  }

  return (
    <View style={styles.filterSection}>
      <Text style={styles.filterSectionTitle}>Filter by Area</Text>
      <View style={styles.filterRow}>
        {(['phase', 'block', 'street'] as FilterField[]).map((field) => (
          <TouchableOpacity
            key={field}
            style={[styles.filterChip, filters[field] && styles.filterChipActive]}
            onPress={() => onSelectFilter(field)}
          >
            <Text style={[styles.filterChipLabel, filters[field] && styles.filterChipLabelActive]}>
              {FILTER_LABELS[field]}
            </Text>
            <Text style={[styles.filterChipValue, filters[field] && styles.filterChipValueActive]}>
              {activeFilterLabel(field)}
            </Text>
          </TouchableOpacity>
        ))}
        {hasFilters && (
          <TouchableOpacity style={styles.filterClearBtn} onPress={onClearFilters}>
            <Text style={styles.filterClearIcon}>X</Text>
            <Text style={styles.filterClearLabel}>Clear</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  filterSection: {
    marginBottom: 16,
  },
  filterSectionTitle: {
    fontSize: 12,
    color: '#999',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    fontWeight: '600',
    marginBottom: 8,
  },
  filterRow: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  filterChip: {
    backgroundColor: '#fff',
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 14,
    flex: 1,
    borderWidth: 1,
    borderColor: '#E8ECF0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  filterChipActive: {
    backgroundColor: '#1a1a2e',
    borderColor: '#1a1a2e',
  },
  filterChipLabel: {
    fontSize: 9,
    color: '#999',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    fontWeight: '600',
  },
  filterChipLabelActive: {
    color: 'rgba(255,255,255,0.6)',
  },
  filterChipValue: {
    fontSize: 13,
    color: '#333',
    fontWeight: '600',
    marginTop: 2,
  },
  filterChipValueActive: {
    color: '#fff',
  },
  filterClearBtn: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 12,
  },
  filterClearIcon: {
    fontSize: 14,
    fontWeight: '800',
    color: '#e94560',
  },
  filterClearLabel: {
    fontSize: 9,
    color: '#e94560',
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.3,
    marginTop: 1,
  },
});
