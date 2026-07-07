import { useState } from 'react';
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import type { ReadingRow } from '@/db/database';

interface Props {
  readings: ReadingRow[];
}

export default function ReadingHistoryPill({ readings }: Props) {
  const [open, setOpen] = useState(false);

  if (readings.length === 0) return null;

  const last = readings[0];

  return (
    <>
      <View style={styles.lastCard}>
        <Text style={styles.lastLabel}>Last Reading</Text>
        <Text style={styles.lastValue}>{last.reading_value.toFixed(1)} m³</Text>
        <Text style={styles.lastDate}>
          {new Date(last.timestamp * 1000).toLocaleDateString()}
          {last.reader_id ? ` by ${last.reader_id}` : ''}
        </Text>
      </View>

      <Pressable style={styles.pill} onPress={() => setOpen(true)}>
        <Text style={styles.pillIcon}>{'\uD83D\uDCCA'}</Text>
        <Text style={styles.pillLabel}>
          View History ({readings.length} reading{readings.length !== 1 ? 's' : ''})
        </Text>
      </Pressable>

      <Modal
        visible={open}
        transparent
        animationType="fade"
        onRequestClose={() => setOpen(false)}
      >
        <View style={styles.overlay}>
          <View style={styles.modal}>
            <Text style={styles.title}>Reading History</Text>
            <ScrollView style={styles.list} nestedScrollEnabled>
              {readings.map((r) => (
                <View key={r.server_id ?? `local-${r.id}`} style={styles.row}>
                  <View style={styles.rowLeft}>
                    <Text style={styles.rowValue}>
                      {r.reading_value.toFixed(1)} m³
                    </Text>
                    <Text style={styles.rowDate}>
                      {new Date(r.timestamp * 1000).toLocaleDateString()}
                    </Text>
                  </View>
                  <View style={styles.rowRight}>
                    {r.reader_id ? (
                      <Text style={styles.readerName}>{r.reader_id}</Text>
                    ) : null}
                    {!r.synced ? (
                      <Text style={styles.pendingBadge}>pending</Text>
                    ) : null}
                  </View>
                </View>
              ))}
            </ScrollView>
            <TouchableOpacity
              style={styles.closeBtn}
              onPress={() => setOpen(false)}
            >
              <Text style={styles.closeBtnText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  lastCard: {
    backgroundColor: '#E8F0FE',
    borderRadius: 12,
    padding: 16,
    marginTop: 4,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#C4D7F2',
  },
  lastLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: '#4A90D9',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  lastValue: {
    fontSize: 28,
    fontWeight: '700',
    color: '#1A1A2E',
  },
  lastDate: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#1A1A2E',
    paddingVertical: 10,
    paddingHorizontal: 18,
    borderRadius: 20,
    gap: 8,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.15,
    shadowRadius: 3,
  },
  pillIcon: {
    fontSize: 16,
  },
  pillLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#fff',
    letterSpacing: 0.3,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modal: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    width: '85%',
    maxHeight: '70%',
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1A1A2E',
    textAlign: 'center',
    marginBottom: 14,
  },
  list: {
    maxHeight: 350,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E8ECF0',
  },
  rowLeft: {
    gap: 2,
  },
  rowValue: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
  },
  rowDate: {
    fontSize: 12,
    color: '#999',
  },
  rowRight: {
    alignItems: 'flex-end',
    gap: 2,
  },
  readerName: {
    fontSize: 11,
    color: '#4A90D9',
    fontWeight: '500',
  },
  pendingBadge: {
    fontSize: 10,
    fontWeight: '600',
    color: '#F5A623',
    textTransform: 'uppercase',
  },
  closeBtn: {
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  closeBtnText: {
    fontSize: 15,
    color: '#4A90D9',
    fontWeight: '600',
  },
});
