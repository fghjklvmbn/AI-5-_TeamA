import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';
import type { ConversationMode } from '../types';

const OPTIONS: Array<{ id: ConversationMode; icon: string; label: string }> = [
  { id: 'live', icon: '◉', label: '실시간' },
  { id: 'chat', icon: '≡', label: '채팅' },
  { id: 'hybrid', icon: '◫', label: '하이브리드' },
];

export function ConversationModeTabs({ value, onChange, compact = false }: {
  value: ConversationMode;
  onChange: (mode: ConversationMode) => void;
  compact?: boolean;
}) {
  const { colors } = useTheme();
  const styles = createStyles(colors, compact);
  return <View accessibilityRole="tablist" style={styles.root}>
    {OPTIONS.map((option) => <Pressable
      accessibilityLabel={`${option.label} 대화 모드`}
      accessibilityRole="tab"
      accessibilityState={{ selected: value === option.id }}
      key={option.id}
      onPress={() => onChange(option.id)}
      style={styles.tabWrap}
    >
      <View style={[styles.circle, value === option.id && styles.circleActive]}>
        <Text style={[styles.icon, value === option.id && styles.iconActive]}>{option.icon}</Text>
      </View>
      <Text style={[styles.label, value === option.id && styles.labelActive]}>{option.label}</Text>
    </Pressable>)}
  </View>;
}

const createStyles = (colors: ThemeColors, compact: boolean) => StyleSheet.create({
  root: { minHeight: compact ? 58 : 72, flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: compact ? 18 : 30, paddingVertical: compact ? 5 : 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: colors.surface },
  tabWrap: { minWidth: compact ? 48 : 55, alignItems: 'center', gap: compact ? 2 : 4 },
  circle: { width: compact ? 32 : 38, height: compact ? 32 : 38, borderRadius: compact ? 16 : 19, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.input },
  circleActive: { borderColor: colors.primary, backgroundColor: colors.primary },
  icon: { color: colors.muted, fontSize: compact ? 15 : 17, fontWeight: '900' },
  iconActive: { color: '#FFFFFF' },
  label: { color: colors.muted, fontSize: 9, fontWeight: '700' },
  labelActive: { color: colors.primaryDark, fontWeight: '900' },
});
