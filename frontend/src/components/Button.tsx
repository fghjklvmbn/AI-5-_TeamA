import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';

export interface ButtonProps {
  label: string;
  onPress: () => void | Promise<void>;
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  loading?: boolean;
  icon?: string;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled,
  loading,
  icon,
}: ButtonProps) {
  const { colors } = useTheme();
  const styles = createStyles(colors);

  const getVariantStyle = () => {
    switch (variant) {
      case 'secondary': return styles.secondaryButton;
      case 'danger': return styles.dangerButton;
      default: return styles.primaryButton;
    }
  };

  const getTextStyle = () => {
    switch (variant) {
      case 'secondary': return styles.secondaryButtonText;
      case 'danger': return styles.dangerButtonText;
      default: return styles.primaryButtonText;
    }
  };

  return (
    <Pressable
      style={({ pressed }) => [getVariantStyle(), styles.button, disabled || loading && styles.disabledButton, pressed && styles.pressedButton]}
      onPress={onPress}
      disabled={disabled || loading}
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading }}
    >
      {loading && <ActivityIndicator color={colors.surface} />}
      {!loading && icon && <Text style={styles.buttonIcon}>{icon}</Text>}
      <Text style={getTextStyle()}>{label}</Text>
    </Pressable>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  button: {
    minHeight: 48,
    borderRadius: 24,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  primaryButton: { backgroundColor: colors.primary },
  secondaryButton: { backgroundColor: colors.secondary },
  dangerButton: { backgroundColor: colors.error },
  disabledButton: { opacity: 0.5 },
  pressedButton: { opacity: 0.9 },
  buttonText: { color: colors.surface, fontSize: 16, fontWeight: '600' },
  primaryButtonText: { color: colors.surface, fontSize: 16, fontWeight: '600' },
  secondaryButtonText: { color: colors.surface, fontSize: 16, fontWeight: '600' },
  dangerButtonText: { color: colors.surface, fontSize: 16, fontWeight: '600' },
  buttonIcon: { fontSize: 20 },
});
