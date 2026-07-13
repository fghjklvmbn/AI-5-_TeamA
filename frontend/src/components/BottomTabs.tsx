import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '../theme';

export type Tab = 'home' | 'chat' | 'memory' | 'settings';

const tabs: { key: Tab; icon: string; label: string }[] = [
  { key: 'home', icon: '◉', label: '메인' },
  { key: 'chat', icon: '▱', label: '채팅' },
  { key: 'memory', icon: '◇', label: '기억' },
  { key: 'settings', icon: '⚙', label: '설정' },
];

export function BottomTabs({ current, onChange }: { current: Tab; onChange: (tab: Tab) => void }) {
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

const styles = StyleSheet.create({
  bar: {
    minHeight: 72,
    paddingHorizontal: 10,
    paddingBottom: 8,
    paddingTop: 7,
    backgroundColor: colors.surface,
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
  },
  item: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 3, borderRadius: 18 },
  activeItem: { backgroundColor: colors.primarySoft },
  icon: { color: colors.muted, fontSize: 20, lineHeight: 23 },
  label: { color: colors.muted, fontSize: 11, fontWeight: '600' },
  activeText: { color: colors.primaryDark },
});

