import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../api';
import { unlockWebAudio } from '../audioPlayback';
import { RecordingOrb } from '../components/RecordingOrb';
import { useLiveRecorder } from '../hooks/useLiveRecorder';
import { useTheme, type ThemeColors } from '../theme';
import type { ChatResponse, Persona, ReasoningEffort, User, Voice } from '../types';

type Props = {
  token: string;
  user: User;
  casualMode: boolean;
  persona: Persona;
  voiceId?: string;
  voiceReplyEnabled: boolean;
  internetEnabled: boolean;
  thinkingMode: boolean;
  reasoningEffort: ReasoningEffort;
  onPersonaChange: (persona: Persona) => void;
  onVoiceIdChange: (voiceId: string | undefined) => void;
  onConversation: (response: ChatResponse) => void;
  onVoiceProcessingChange: (active: boolean, transcript?: string) => void;
  onOpenAccount: () => void;
  onLogout: () => Promise<void>;
};

type DropdownOption = { id: string; label: string; detail?: string };

function DropdownField({
  label,
  value,
  options,
  onSelect,
}: {
  label: string;
  value: string;
  options: DropdownOption[];
  onSelect: (id: string) => void;
}) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const [open, setOpen] = useState(false);
  const selected = options.find((option) => option.id === value) ?? options[0];

  return (
    <View style={[styles.dropdownField, open && styles.dropdownFieldOpen]}>
      <Text style={styles.sectionLabel}>{label}</Text>
      <Pressable onPress={() => setOpen((current) => !current)} style={[styles.dropdownButton, open && styles.dropdownButtonOpen]}>
        <Text numberOfLines={1} style={styles.dropdownValue}>{selected?.label ?? '선택하기'}</Text>
        <Text style={styles.dropdownChevron}>{open ? '⌃' : '⌄'}</Text>
      </Pressable>
      {open && (
        <View style={styles.dropdownMenu}>
          <ScrollView nestedScrollEnabled style={styles.dropdownScroll}>
            {options.map((option) => (
              <Pressable
                key={option.id}
                onPress={() => { onSelect(option.id); setOpen(false); }}
                style={[styles.dropdownOption, option.id === value && styles.dropdownOptionActive]}
              >
                <Text numberOfLines={1} style={[styles.dropdownOptionText, option.id === value && styles.dropdownOptionTextActive]}>{option.label}</Text>
                {!!option.detail && <Text numberOfLines={1} style={styles.dropdownOptionDetail}>{option.detail}</Text>}
              </Pressable>
            ))}
          </ScrollView>
        </View>
      )}
    </View>
  );
}

export function HomeScreen({ token, user, casualMode, persona, voiceId, voiceReplyEnabled, internetEnabled, thinkingMode, reasoningEffort, onPersonaChange, onVoiceIdChange, onConversation, onVoiceProcessingChange, onOpenAccount, onLogout }: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const recorder = useLiveRecorder(token);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [processing, setProcessing] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [status, setStatus] = useState('가운데 버튼을 누르고 편하게 말해 보세요.');
  const mountedRef = useRef(true);

  const voiceOptions: DropdownOption[] = (voices.length
    ? voices
    : [{ id: 'default', voice_name: '기본 음성', is_default: true, is_personalized: false }]
  ).map((voice) => ({
    id: voice.id,
    label: voice.voice_name,
    detail: voice.is_default ? '공용 기본 음성' : '개인화 음성',
  }));
  const personaOptions: DropdownOption[] = [
    { id: 'default', label: '기본', detail: '일반 AI 도우미' },
    { id: 'emotional_companion', label: '정서적 동반자', detail: '공감 중심 대화' },
    { id: 'none', label: '없음', detail: '역할 설정 없는 일반 채팅' },
  ];

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    let active = true;
    void api.voices(token).then((items) => {
      if (!active) return;
      setVoices(items);
      if (!voiceId || !items.some((voice) => voice.id === voiceId)) {
        onVoiceIdChange((items.find((voice) => voice.is_default) ?? items[0])?.id);
      }
    }).catch(() => {
      if (active) setVoices([]);
    });
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    if (!profileMenuOpen || Platform.OS !== 'web' || typeof document === 'undefined') return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setProfileMenuOpen(false);
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [profileMenuOpen]);

  const toggleRecording = async () => {
    if (recorder.isRecording) unlockWebAudio();
    try {
      if (!recorder.isRecording) {
        setStatus('음성을 듣고 있어요. 자연스럽게 말씀해 주세요.');
        await recorder.start();
        return;
      }
      setProcessing(true);
      onVoiceProcessingChange(true);
      setStatus('기억을 살펴보고 답변을 만들고 있어요…');
      const transcript = await recorder.stop();
      if (!mountedRef.current) return;
      if (!transcript) {
        setStatus('잘 들리지 않았어요. 조금 더 가까이에서 다시 말해 주세요.');
        return;
      }
      onVoiceProcessingChange(true, transcript);
      // Voice conversations started from Home always begin in a fresh chat session.
      const response = await api.chat(
        token, transcript, undefined, voiceId, voiceReplyEnabled, casualMode, persona, internetEnabled, thinkingMode,
        reasoningEffort,
      );
      if (!mountedRef.current) return;
      setStatus('답변이 준비됐어요.');
      onConversation(response);
    } catch (reason) {
      if (mountedRef.current) {
        setStatus(reason instanceof Error ? reason.message : '음성 대화를 시작하지 못했어요.');
      }
    } finally {
      if (mountedRef.current) setProcessing(false);
      onVoiceProcessingChange(false);
    }
  };

  return (<>
    <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>안녕하세요, {user.display_name}님</Text>
          <Text style={styles.headline}>오늘은 어떤 이야기를{`\n`}나눠볼까요?</Text>
        </View>
        <Pressable
          accessibilityLabel="프로필 메뉴 열기"
          accessibilityRole="button"
          onPress={() => setProfileMenuOpen((current) => !current)}
          style={({ pressed }) => [styles.avatar, pressed && styles.avatarPressed]}
        >
          <Text style={styles.avatarText}>{user.display_name.slice(0, 1)}</Text>
          <View style={styles.profileIndicator} />
        </Pressable>
      </View>

      <View style={styles.orbArea}>
        <RecordingOrb
          amplitude={recorder.amplitude}
          disabled={processing}
          onPress={() => void toggleRecording()}
          recording={recorder.isRecording}
        />
        {processing && <ActivityIndicator color={colors.primary} style={styles.spinner} />}
        <Text style={styles.status}>{status}</Text>
      </View>

      {(recorder.isRecording || !!recorder.liveText) && (
        <View style={styles.transcriptCard}>
          <View style={styles.liveRow}>
            <View style={styles.liveDot} />
            <Text style={styles.liveLabel}>{recorder.isRecording ? '전체 녹음 중' : '인식된 내용'}</Text>
          </View>
          <Text style={styles.transcript}>
            {recorder.liveText || `정지하면 ${Math.max(1, Math.round(recorder.durationMillis / 1000))}초의 전체 녹음을 한 번에 인식해요.`}
          </Text>
        </View>
      )}

      <View style={styles.selectorSection}>
        <View style={styles.selectorRow}>
          <DropdownField
            label="응답 음성"
            onSelect={(id) => onVoiceIdChange(id === 'default' ? undefined : id)}
            options={voiceOptions}
            value={voiceId ?? 'default'}
          />
          <DropdownField
            label="페르소나"
            onSelect={(id) => onPersonaChange(id as Persona)}
            options={personaOptions}
            value={persona}
          />
        </View>
      </View>
    </ScrollView>
    <Modal animationType="fade" onRequestClose={() => setProfileMenuOpen(false)} transparent visible={profileMenuOpen}>
      <Pressable accessibilityLabel="프로필 메뉴 닫기" onPress={() => setProfileMenuOpen(false)} style={styles.profileOverlay}>
        <View pointerEvents="box-none" style={styles.profileViewport}>
          <Pressable accessibilityRole="menu" onPress={(event) => event.stopPropagation()} style={styles.profileMenu}>
            <View style={styles.profileSummary}>
              <View style={styles.profileMenuAvatar}><Text style={styles.profileMenuAvatarText}>{user.display_name.slice(0, 1)}</Text></View>
              <View style={styles.profileSummaryCopy}>
                <Text numberOfLines={1} style={styles.profileName}>{user.display_name}</Text>
                <Text numberOfLines={1} style={styles.profileEmail}>{user.email}</Text>
              </View>
            </View>
            <View style={styles.profileDivider} />
            <Pressable
              accessibilityRole="menuitem"
              onPress={() => { setProfileMenuOpen(false); onOpenAccount(); }}
              style={({ pressed }) => [styles.profileAction, pressed && styles.profileActionPressed]}
            >
              <View style={styles.profileActionIcon}><Text style={styles.profileActionIconText}>✎</Text></View>
              <View style={styles.profileActionCopy}><Text style={styles.profileActionTitle}>정보 변경</Text><Text style={styles.profileActionDescription}>닉네임과 비밀번호 관리</Text></View>
              <Text style={styles.profileChevron}>›</Text>
            </Pressable>
            <Pressable
              accessibilityRole="menuitem"
              onPress={() => { setProfileMenuOpen(false); void onLogout(); }}
              style={({ pressed }) => [styles.profileAction, pressed && styles.profileActionPressed]}
            >
              <View style={[styles.profileActionIcon, styles.logoutIcon]}><Text style={styles.logoutIconText}>↪</Text></View>
              <View style={styles.profileActionCopy}><Text style={styles.logoutTitle}>로그아웃</Text><Text style={styles.profileActionDescription}>현재 기기에서 안전하게 종료</Text></View>
            </Pressable>
          </Pressable>
        </View>
      </Pressable>
    </Modal>
  </>);
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  content: { flexGrow: 1, padding: 24, paddingBottom: 34 },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  greeting: { color: colors.primaryDark, fontSize: 13, fontWeight: '700', marginBottom: 6 },
  headline: { color: colors.ink, fontSize: 27, lineHeight: 35, fontWeight: '900', letterSpacing: -0.8 },
  avatar: { width: 42, height: 42, borderRadius: 16, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', position: 'relative', borderWidth: 1, borderColor: colors.lilac },
  avatarPressed: { opacity: 0.72, transform: [{ scale: 0.97 }] },
  avatarText: { color: colors.primaryDark, fontWeight: '800', fontSize: 17 },
  profileIndicator: { position: 'absolute', right: -1, bottom: -1, width: 11, height: 11, borderRadius: 99, borderWidth: 2, borderColor: colors.surface, backgroundColor: colors.success },
  profileOverlay: { flex: 1, alignItems: 'center', backgroundColor: 'rgba(16, 11, 23, 0.22)' },
  profileViewport: { width: '100%', maxWidth: 560, flex: 1, position: 'relative' },
  profileMenu: { position: 'absolute', top: 69, right: 20, width: 258, borderRadius: 20, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 10, shadowColor: '#1A1025', shadowOffset: { width: 0, height: 13 }, shadowOpacity: 0.2, shadowRadius: 28, elevation: 20 },
  profileSummary: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 7, paddingVertical: 8 },
  profileMenuAvatar: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft },
  profileMenuAvatarText: { color: colors.primaryDark, fontSize: 15, fontWeight: '900' },
  profileSummaryCopy: { flex: 1, minWidth: 0 },
  profileName: { color: colors.ink, fontSize: 13, fontWeight: '900' },
  profileEmail: { color: colors.muted, fontSize: 9, marginTop: 3 },
  profileDivider: { height: 1, backgroundColor: colors.border, marginVertical: 6 },
  profileAction: { minHeight: 58, flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 13, paddingHorizontal: 8, paddingVertical: 7 },
  profileActionPressed: { backgroundColor: colors.subtle },
  profileActionIcon: { width: 34, height: 34, borderRadius: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft },
  profileActionIconText: { color: colors.primaryDark, fontSize: 15, fontWeight: '900' },
  profileActionCopy: { flex: 1 },
  profileActionTitle: { color: colors.ink, fontSize: 12, fontWeight: '900' },
  profileActionDescription: { color: colors.muted, fontSize: 8, marginTop: 3 },
  profileChevron: { color: colors.muted, fontSize: 22, fontWeight: '400' },
  logoutIcon: { backgroundColor: colors.dangerSoft },
  logoutIconText: { color: colors.danger, fontSize: 17, fontWeight: '900' },
  logoutTitle: { color: colors.danger, fontSize: 12, fontWeight: '900' },
  orbArea: { alignItems: 'center', marginTop: 34 },
  spinner: { position: 'absolute', top: 106 },
  status: { color: colors.muted, textAlign: 'center', fontSize: 13, marginTop: 4, minHeight: 38, maxWidth: 300, lineHeight: 19 },
  transcriptCard: { backgroundColor: colors.primarySoft, borderRadius: 22, padding: 18, marginTop: 15, borderWidth: 1, borderColor: colors.lilac },
  liveRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 9 },
  liveDot: { width: 8, height: 8, borderRadius: 99, backgroundColor: colors.primary },
  liveLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: '800' },
  transcript: { color: colors.ink, fontSize: 15, lineHeight: 23 },
  selectorSection: { marginTop: 24, zIndex: 20 },
  selectorRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  dropdownField: { flex: 1 },
  dropdownFieldOpen: { zIndex: 30 },
  sectionLabel: { color: colors.ink, fontWeight: '800', fontSize: 14, marginBottom: 10 },
  dropdownButton: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderWidth: 1, borderColor: colors.border, borderRadius: 15, backgroundColor: colors.surface, paddingHorizontal: 13 },
  dropdownButtonOpen: { borderColor: colors.primary },
  dropdownValue: { flex: 1, color: colors.ink, fontSize: 12, fontWeight: '800' },
  dropdownChevron: { color: colors.primaryDark, fontSize: 16, fontWeight: '900' },
  dropdownMenu: { marginTop: 6, zIndex: 40, elevation: 12, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 5, shadowColor: '#2E2438', shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.16, shadowRadius: 14 },
  dropdownScroll: { maxHeight: 220 },
  dropdownOption: { minHeight: 48, justifyContent: 'center', borderRadius: 11, paddingHorizontal: 10, paddingVertical: 7 },
  dropdownOptionActive: { backgroundColor: colors.primarySoft },
  dropdownOptionText: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  dropdownOptionTextActive: { color: colors.primaryDark, fontWeight: '900' },
  dropdownOptionDetail: { color: colors.muted, fontSize: 9, marginTop: 3 },
});
