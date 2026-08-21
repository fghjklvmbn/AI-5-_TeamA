import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';

export interface InputFieldProps {
  label: string;
  value: string;
  placeholder?: string;
  secureTextEntry?: boolean;
  onChangeText: (text: string) => void;
  error?: string;
  disabled?: boolean;
  autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
  autoCorrect?: boolean;
}

export function InputField({
  label,
  value,
  placeholder,
  secureTextEntry,
  onChangeText,
  error,
  disabled,
  autoCapitalize = 'sentences',
  autoCorrect = false,
}: InputFieldProps) {
  const { colors } = useTheme();
  const styles = createStyles(colors);

  return (
    <View style={styles.container}>
      <Text style={styles.label}>{label}</Text>
      <View style={[styles.inputWrapper, disabled && styles.disabledInputWrapper]}>
        <TextInput
          style={styles.input}
          value={value}
          placeholder={placeholder ?? label}
          accessibilityLabel={label}
          placeholderTextColor={colors.muted}
          onChangeText={onChangeText}
          secureTextEntry={secureTextEntry}
          editable={!disabled}
          autoCapitalize={autoCapitalize}
          autoCorrect={autoCorrect}
          numberOfLines={1}
        />
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  container: { marginBottom: 16 },
  label: { color: colors.ink, fontSize: 14, fontWeight: '600', marginBottom: 6 },
  inputWrapper: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, overflow: 'hidden' },
  disabledInputWrapper: { borderColor: colors.muted },
  input: {
    color: colors.ink,
    fontSize: 16,
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  error: { color: colors.danger, fontSize: 12, marginTop: 4, fontStyle: 'italic' },
});
