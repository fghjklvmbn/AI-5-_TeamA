import React from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';

export type Tab = 'home' | 'chat' | 'memory' | 'portrait' | 'settings';

const tabs: { key: Tab; icon: string; label: string }[] = [
  { key: 'home', icon: '◉', label: '메인' },
  { key: 'chat', icon: '▱', label: '채팅' },
  { key: 'memory', icon: '◇', label: '기억' },
  { key: 'portrait', icon: '◐', label: '자화상' },
  { key: 'settings', icon: '⚙', label: '설정' },
];

export function BottomTabs({ current, onChange }: { current: Tab; onChange: (tab: Tab) => void }) {
  const { colors } = useTheme();
  const { width } = useWindowDimensions();
  const styles = createStyles(colors, width <= 480);
  return (
    <View style={styles.bar}>
      {tabs.map((tab) => {
        const active = tab.key === current;
        return (
          <Pressable
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            key={tab.key}
            onPress={() => onChange(tab.key)}
            style={[styles.item, active && styles.activeItem]}
          >
            <Text style={[styles.icon, active && styles.activeText]}>{tab.icon}</Text>
            <Text style={[styles.label, active && styles.activeText]}>{tab.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const createStyles = (colors: ThemeColors, compact: boolean) => StyleSheet.create({
  bar: {
    minHeight: compact ? 62 : 72,
    paddingHorizontal: compact ? 5 : 10,
    paddingBottom: compact ? 5 : 8,
    paddingTop: compact ? 5 : 7,
    backgroundColor: colors.surface,
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
  },
  item: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: compact ? 1 : 3, borderRadius: compact ? 14 : 18 },
  activeItem: { backgroundColor: colors.primarySoft },
  icon: { color: colors.muted, fontSize: compact ? 17 : 20, lineHeight: compact ? 20 : 23 },
  label: { color: colors.muted, fontSize: compact ? 9 : 11, fontWeight: '600' },
  activeText: { color: colors.primaryDark },
});

