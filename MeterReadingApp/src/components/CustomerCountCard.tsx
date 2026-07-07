import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

interface CustomerCountCardProps {
  customerCount: number;
  unreadCount: number;
  hasFilters: boolean;
  onViewUnread: () => void;
}

export default function CustomerCountCard({
  customerCount,
  unreadCount,
  hasFilters,
  onViewUnread,
}: CustomerCountCardProps) {
  return (
    <View style={styles.countCard}>
      <Text style={styles.countLabel}>
        {hasFilters ? 'Filtered Customers' : 'Total Customers'}
      </Text>
      <Text style={styles.countValue}>
        {customerCount > 0 ? `${customerCount}` : '0'}
      </Text>
      {customerCount > 0 && (
        <TouchableOpacity style={styles.unreadBtn} onPress={onViewUnread}>
          <Text style={styles.unreadBtnIcon}>{'\u{1F4ED}'}</Text>
          <Text style={styles.unreadBtnText}>{unreadCount} Unread This Month</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  countCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 3,
  },
  countLabel: {
    fontSize: 13,
    color: '#888',
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontWeight: '600',
  },
  countValue: {
    fontSize: 48,
    fontWeight: '800',
    color: '#1a1a2e',
    marginTop: 8,
    marginBottom: 12,
  },
  unreadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF3E0',
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: '#FFE0B2',
  },
  unreadBtnIcon: {
    fontSize: 16,
    marginRight: 8,
  },
  unreadBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#E65100',
  },
});
