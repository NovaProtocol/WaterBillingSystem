import { StyleSheet, Text, TextInput, View } from 'react-native';

interface ReadingInputProps {
  value: string;
  onChangeText: (text: string) => void;
  disabled?: boolean;
}

export default function ReadingInput({ value, onChangeText, disabled }: ReadingInputProps) {
  return (
    <View>
      <Text style={styles.inputLabel}>Current Reading (m³)</Text>
      <TextInput
        style={styles.readingInput}
        placeholder="0.0"
        placeholderTextColor="#999"
        value={value}
        onChangeText={onChangeText}
        keyboardType="decimal-pad"
        autoFocus
        editable={!disabled}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 6,
  },
  readingInput: {
    borderWidth: 1,
    borderColor: '#DDD',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
    backgroundColor: '#FAFAFA',
    marginBottom: 12,
  },
});
