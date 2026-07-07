import { FlatList, Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { CustomerRow } from '@/db/database';

interface UnreadListModalProps {
  visible: boolean;
  unreadList: CustomerRow[];
  onClose: () => void;
  onSelectCustomer: (customerNumber: string) => void;
}

export default function UnreadListModal({
  visible,
  unreadList,
  onClose,
  onSelectCustomer,
}: UnreadListModalProps) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <View style={styles.modalContainer}>
          <Text style={styles.modalTitle}>Unread This Month</Text>
          <Text style={styles.modalSubtitle}>
            {unreadList.length} customer{unreadList.length !== 1 ? 's' : ''} not yet read
          </Text>
          {unreadList.length === 0 ? (
            <Text style={styles.emptyText}>All customers have been read this month.</Text>
          ) : (
            <FlatList
              data={unreadList}
              keyExtractor={(item) => item.customer_number}
              style={styles.unreadList}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={styles.unreadRow}
                  onPress={() => { onClose(); onSelectCustomer(item.customer_number); }}
                >
                  <Text style={styles.unreadName}>{item.name}</Text>
                  <Text style={styles.unreadNumber}>{item.customer_number}</Text>
                </TouchableOpacity>
              )}
            />
          )}
          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeBtnText}>Close</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContainer: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 24,
    paddingBottom: 36,
    maxHeight: '75%',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: '#1a1a2e',
    textAlign: 'center',
  },
  modalSubtitle: {
    fontSize: 13,
    color: '#999',
    textAlign: 'center',
    marginTop: 4,
    marginBottom: 20,
  },
  unreadList: {
    maxHeight: 300,
  },
  unreadRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F2F5',
  },
  unreadName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1a1a2e',
    flex: 1,
  },
  unreadNumber: {
    fontSize: 11,
    color: '#aaa',
    fontFamily: 'monospace',
    marginLeft: 8,
  },
  emptyText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    paddingVertical: 32,
  },
  closeBtn: {
    backgroundColor: '#1a1a2e',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 20,
  },
  closeBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
  },
});
