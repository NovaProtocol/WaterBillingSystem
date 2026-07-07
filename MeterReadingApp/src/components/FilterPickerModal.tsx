import { FlatList, Modal, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

interface FilterPickerModalProps {
  visible: boolean;
  title: string;
  options: string[];
  selected: string | undefined;
  onSelect: (value: string | null) => void;
  onClose: () => void;
}

export default function FilterPickerModal({
  visible,
  title,
  options,
  selected,
  onSelect,
  onClose,
}: FilterPickerModalProps) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <View style={styles.modalContainer}>
          <Text style={styles.modalTitle}>Select {title}</Text>
          <FlatList
            data={['', ...options]}
            keyExtractor={(item) => item || '__all__'}
            style={styles.pickerList}
            renderItem={({ item }) => {
              const isActive = item === '' ? !selected : item === selected;
              return (
                <TouchableOpacity
                  style={[styles.pickerRow, isActive && styles.pickerRowActive]}
                  onPress={() => onSelect(item || null)}
                >
                  <Text style={[styles.pickerText, isActive && styles.pickerTextActive]}>
                    {item || `All ${title}`}
                  </Text>
                </TouchableOpacity>
              );
            }}
          />
          <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
            <Text style={styles.closeBtnText}>Cancel</Text>
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
    marginBottom: 20,
  },
  pickerList: {
    maxHeight: 300,
  },
  pickerRow: {
    paddingVertical: 14,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F2F5',
    borderRadius: 8,
  },
  pickerRowActive: {
    backgroundColor: '#1a1a2e',
  },
  pickerText: {
    fontSize: 15,
    color: '#333',
    fontWeight: '500',
  },
  pickerTextActive: {
    color: '#fff',
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
