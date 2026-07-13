import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../api';
import { colors } from '../theme';
import type { User, Voice } from '../types';

function ChoiceRow({ label, options }: { label: string; options: string[] }) {
  const [value, setValue] = useState(options[1] ?? options[0]);
  return (
    <View style={styles.choiceBlock}>
      <Text style={styles.rowLabel}>{label}</Text>
      <View style={styles.choiceRow}>
        {options.map((option) => (
          <Pressable key={option} onPress={() => setValue(option)} style={[styles.choice, value === option && styles.choiceActive]}>
            <Text style={[styles.choiceText, value === option && styles.choiceTextActive]}>{option}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export function SettingsScreen({ token, user, logout }: { token: string; user: User; logout: () => Promise<void> }) {
  const [voices, setVoices] = useState<Voice[]>([]);
  useEffect(() => { void api.voices(token).then(setVoices).catch(() => setVoices([])); }, [token]);

  return (
    <ScrollView contentContainerStyle={styles.root} showsVerticalScrollIndicator={false}>
      <Text style={styles.title}>설정</Text>
      <View style={styles.profileCard}>
        <View style={styles.avatar}><Text style={styles.avatarText}>{user.display_name.slice(0, 1)}</Text></View>
        <View style={{ flex: 1 }}>
          <Text style={styles.name}>{user.display_name}</Text>
          <Text style={styles.email}>{user.email}</Text>
        </View>
        <View style={styles.securePill}><Text style={styles.secureText}>JWT 보호됨</Text></View>
      </View>

      <Text style={styles.sectionTitle}>음성 답변 설정</Text>
      <View style={styles.card}>
        <ChoiceRow label="톤" options={['차분하게', '자연스럽게', '밝게']} />
        <View style={styles.divider} />
        <ChoiceRow label="말하기 속도" options={['느리게', '보통', '빠르게']} />
      </View>

      <Text style={styles.sectionTitle}>개인화 음성</Text>
      <View style={styles.card}>
        {voices.length ? voices.map((voice, index) => (
          <View key={voice.id} style={[styles.voiceRow, index < voices.length - 1 && styles.voiceBorder]}>
            <View style={styles.voiceIcon}><Text style={styles.voiceIconText}>♪</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.voiceName}>{voice.voice_name}</Text>
              <Text numberOfLines={1} style={styles.voiceDesc}>{voice.description || '등록된 개인화 음성'}</Text>
            </View>
          </View>
        )) : <Text style={styles.emptyVoice}>아카이브 서버에 등록된 음성이 표시됩니다.</Text>}
      </View>

      <Text style={styles.sectionTitle}>계정</Text>
      <Pressable onPress={() => void logout()} style={styles.logout}>
        <Text style={styles.logoutText}>로그아웃</Text>
      </Pressable>
      <Text style={styles.version}>MemoryPal beta · Python 3.12 API</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { padding: 22, paddingBottom: 38 },
  title: { color: colors.ink, fontSize: 29, fontWeight: '900', marginBottom: 20 },
  profileCard: { flexDirection: 'row', alignItems: 'center', gap: 13, backgroundColor: colors.primarySoft, borderRadius: 22, padding: 16 },
  avatar: { width: 48, height: 48, borderRadius: 17, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#FFFFFF', fontSize: 19, fontWeight: '900' },
  name: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  email: { color: colors.muted, fontSize: 11, marginTop: 3 },
  securePill: { backgroundColor: '#FFFFFF', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 6 },
  secureText: { color: colors.success, fontSize: 9, fontWeight: '800' },
  sectionTitle: { color: colors.ink, fontSize: 14, fontWeight: '900', marginTop: 25, marginBottom: 10 },
  card: { backgroundColor: colors.surface, borderRadius: 20, borderWidth: 1, borderColor: colors.border, padding: 16 },
  choiceBlock: { gap: 11 },
  rowLabel: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  choiceRow: { flexDirection: 'row', gap: 6 },
  choice: { flex: 1, alignItems: 'center', paddingVertical: 9, borderRadius: 11, backgroundColor: '#F5F2F7' },
  choiceActive: { backgroundColor: colors.primarySoft },
  choiceText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  choiceTextActive: { color: colors.primaryDark },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 17 },
  voiceRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  voiceBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  voiceIcon: { width: 39, height: 39, borderRadius: 14, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  voiceIconText: { color: colors.primaryDark, fontSize: 16, fontWeight: '800' },
  voiceName: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  voiceDesc: { color: colors.muted, fontSize: 10, marginTop: 3 },
  emptyVoice: { color: colors.muted, fontSize: 12, textAlign: 'center', paddingVertical: 12 },
  logout: { height: 51, borderRadius: 16, borderWidth: 1, borderColor: '#EDCBD3', backgroundColor: '#FFF7F8', alignItems: 'center', justifyContent: 'center' },
  logoutText: { color: colors.danger, fontSize: 14, fontWeight: '800' },
  version: { color: '#A49DAB', fontSize: 10, textAlign: 'center', marginTop: 22 },
});
