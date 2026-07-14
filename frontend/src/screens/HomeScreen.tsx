import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../api';
import { unlockWebAudio } from '../audioPlayback';
import { RecordingOrb } from '../components/RecordingOrb';
import { useLiveRecorder } from '../hooks/useLiveRecorder';
import { useTheme, type ThemeColors } from '../theme';
import type { ChatResponse, Persona, User, Voice } from '../types';

type Props = {
  token: string;
  user: User;
  casualMode: boolean;
  persona: Persona;
  voiceReplyEnabled: boolean;
  onPersonaChange: (persona: Persona) => void;
  onConversation: (response: ChatResponse) => void;
  onVoiceProcessingChange: (active: boolean, transcript?: string) => void;
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

export function HomeScreen({ token, user, casualMode, persona, voiceReplyEnabled, onPersonaChange, onConversation, onVoiceProcessingChange }: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const recorder = useLiveRecorder(token);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState<string>();
  const [processing, setProcessing] = useState(false);
  const [status, setStatus] = useState('가운데 버튼을 누르고 편하게 말해 보세요.');

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
  ];

  useEffect(() => {
    void api.voices(token).then((items) => {
      setVoices(items);
      setVoiceId((items.find((voice) => voice.is_default) ?? items[0])?.id);
    }).catch(() => setVoices([]));
  }, [token]);

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
      if (!transcript) {
        setStatus('잘 들리지 않았어요. 조금 더 가까이에서 다시 말해 주세요.');
        return;
      }
      onVoiceProcessingChange(true, transcript);
      // Voice conversations started from Home always begin in a fresh chat session.
      const response = await api.chat(token, transcript, undefined, voiceId, true, casualMode, persona);
      setStatus('답변이 준비됐어요.');
      onConversation(response);
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : '음성 대화를 시작하지 못했어요.');
    } finally {
      setProcessing(false);
      onVoiceProcessingChange(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.header}>
        <View>
          <Text style={styles.greeting}>안녕하세요, {user.display_name}님</Text>
          <Text style={styles.headline}>오늘은 어떤 이야기를{`\n`}나눠볼까요?</Text>
        </View>
        <View style={styles.avatar}><Text style={styles.avatarText}>{user.display_name.slice(0, 1)}</Text></View>
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
            onSelect={(id) => setVoiceId(id === 'default' ? undefined : id)}
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
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  content: { flexGrow: 1, padding: 24, paddingBottom: 34 },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  greeting: { color: colors.primaryDark, fontSize: 13, fontWeight: '700', marginBottom: 6 },
  headline: { color: colors.ink, fontSize: 27, lineHeight: 35, fontWeight: '900', letterSpacing: -0.8 },
  avatar: { width: 42, height: 42, borderRadius: 16, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.primaryDark, fontWeight: '800', fontSize: 17 },
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
  dropdownField: { flex: 1, position: 'relative' },
  dropdownFieldOpen: { zIndex: 30 },
  sectionLabel: { color: colors.ink, fontWeight: '800', fontSize: 14, marginBottom: 10 },
  dropdownButton: { minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderWidth: 1, borderColor: colors.border, borderRadius: 15, backgroundColor: colors.surface, paddingHorizontal: 13 },
  dropdownButtonOpen: { borderColor: colors.primary },
  dropdownValue: { flex: 1, color: colors.ink, fontSize: 12, fontWeight: '800' },
  dropdownChevron: { color: colors.primaryDark, fontSize: 16, fontWeight: '900' },
  dropdownMenu: { position: 'absolute', left: 0, right: 0, bottom: 54, zIndex: 40, elevation: 12, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 5, shadowColor: '#2E2438', shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.16, shadowRadius: 14 },
  dropdownScroll: { maxHeight: 220 },
  dropdownOption: { minHeight: 48, justifyContent: 'center', borderRadius: 11, paddingHorizontal: 10, paddingVertical: 7 },
  dropdownOptionActive: { backgroundColor: colors.primarySoft },
  dropdownOptionText: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  dropdownOptionTextActive: { color: colors.primaryDark, fontWeight: '900' },
  dropdownOptionDetail: { color: colors.muted, fontSize: 9, marginTop: 3 },
});
