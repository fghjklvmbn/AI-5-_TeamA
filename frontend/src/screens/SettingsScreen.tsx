import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { BlurView } from 'expo-blur';
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { api } from '../api';
import { useTheme, type ThemeColors } from '../theme';
import type { Persona, User, Voice, VoiceStatus } from '../types';

function ChoiceRow({ label, options }: { label: string; options: string[] }) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
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

type Props = {
  token: string;
  user: User;
  casualMode: boolean;
  persona: Persona;
  darkMode: boolean;
  voiceReplyEnabled: boolean;
  onCasualModeChange: (enabled: boolean) => void;
  onPersonaChange: (persona: Persona) => void;
  onDarkModeChange: (enabled: boolean) => void;
  onVoiceReplyChange: (enabled: boolean) => void;
  logout: () => Promise<void>;
};

export function SettingsScreen({
  token,
  user,
  casualMode,
  persona,
  darkMode,
  voiceReplyEnabled,
  onCasualModeChange,
  onPersonaChange,
  onDarkModeChange,
  onVoiceReplyChange,
  logout,
}: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const sampleRecorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const sampleState = useAudioRecorderState(sampleRecorder, 250);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>();
  const [showVoiceForm, setShowVoiceForm] = useState(false);
  const [voiceName, setVoiceName] = useState('');
  const [referenceText, setReferenceText] = useState('안녕하세요. 오늘도 편안하고 좋은 하루 보내세요.');
  const [description, setDescription] = useState('');
  const [sampleUri, setSampleUri] = useState<string>();
  const [recording, setRecording] = useState(false);
  const [saving, setSaving] = useState(false);
  const [voiceMessage, setVoiceMessage] = useState('');

  const loadVoices = useCallback(() => {
    void api.voices(token).then(setVoices).catch(() => setVoices([]));
    void api.voiceStatus(token).then(setVoiceStatus).catch(() => setVoiceStatus(undefined));
  }, [token]);

  useEffect(loadVoices, [loadVoices]);

  const toggleSampleRecording = async () => {
    try {
      setVoiceMessage('');
      if (recording) {
        await sampleRecorder.stop();
        const recordedUri = sampleRecorder.uri;
        if (!recordedUri) throw new Error('녹음 파일을 만들지 못했습니다. 다시 녹음해 주세요.');
        setRecording(false);
        setSampleUri(recordedUri);
        await setAudioModeAsync({ allowsRecording: false });
        setVoiceMessage('샘플 녹음이 준비됐어요. 입력한 문장과 녹음 내용이 같은지 확인해 주세요.');
        return;
      }
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) throw new Error('개인화 음성을 만들려면 마이크 권한이 필요합니다.');
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await sampleRecorder.prepareToRecordAsync();
      sampleRecorder.record();
      setSampleUri(undefined);
      setRecording(true);
      setVoiceMessage('아래 참조 문장을 자연스럽게 읽고 녹음을 완료해 주세요.');
    } catch (reason) {
      setRecording(false);
      setVoiceMessage(reason instanceof Error ? reason.message : '녹음을 시작하지 못했습니다.');
    }
  };

  const saveVoice = async () => {
    if (!voiceName.trim()) {
      setVoiceMessage('음성 이름을 입력해 주세요.');
      return;
    }
    if (referenceText.trim().length < 2) {
      setVoiceMessage('녹음에서 읽은 참조 문장을 입력해 주세요.');
      return;
    }
    if (!sampleUri) {
      setVoiceMessage('먼저 음성 샘플을 녹음해 주세요.');
      return;
    }
    setSaving(true);
    setVoiceMessage('개인화 음성을 등록하고 있어요...');
    try {
      const voice = await api.createVoice(
        token,
        sampleUri,
        voiceName.trim(),
        referenceText.trim(),
        description.trim(),
      );
      setVoices((current) => [voice, ...current.filter((item) => item.id !== voice.id)]);
      setVoiceName('');
      setDescription('');
      setSampleUri(undefined);
      setShowVoiceForm(false);
      setVoiceMessage('개인화 음성이 등록됐어요.');
    } catch (reason) {
      setVoiceMessage(reason instanceof Error ? reason.message : '개인화 음성을 등록하지 못했습니다.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.root} showsVerticalScrollIndicator={false}>
      <Text style={styles.title}>설정</Text>
      <View style={styles.profileCard}>
        <View style={styles.avatar}><Text style={styles.avatarText}>{user.display_name.slice(0, 1)}</Text></View>
        <View style={{ flex: 1 }}>
          <Text style={styles.name}>{user.display_name}</Text>
          <Text style={styles.email}>{user.email}</Text>
        </View>
      </View>

      <Text style={styles.sectionTitle}>화면 설정</Text>
      <View style={styles.card}>
        <View style={styles.switchRow}>
          <View style={styles.switchCopy}>
            <Text style={styles.rowLabel}>다크 모드</Text>
            <Text style={styles.switchDescription}>
              {darkMode ? '어두운 화면으로 눈의 피로를 줄여요.' : '밝은 기본 화면을 사용해요.'}
            </Text>
          </View>
          <Switch
            accessibilityLabel="다크 모드"
            onValueChange={onDarkModeChange}
            thumbColor="#FFFFFF"
            trackColor={{ false: colors.border, true: colors.primary }}
            value={darkMode}
          />
        </View>
      </View>

      <Text style={styles.sectionTitle}>페르소나</Text>
      <View style={styles.card}>
        <Pressable
          onPress={() => onPersonaChange('default')}
          style={[styles.personaOption, persona === 'default' && styles.personaOptionActive]}
        >
          <View style={styles.personaHeader}>
            <Text style={styles.personaTitle}>기본</Text>
            {persona === 'default' && <Text style={styles.personaSelected}>선택됨</Text>}
          </View>
          <Text style={styles.personaDescription}>정확하고 실용적인 일반 AI 도우미</Text>
        </Pressable>
        <View style={styles.divider} />
        <Pressable
          onPress={() => onPersonaChange('emotional_companion')}
          style={[styles.personaOption, persona === 'emotional_companion' && styles.personaOptionActive]}
        >
          <View style={styles.personaHeader}>
            <Text style={styles.personaTitle}>정서적 동반자</Text>
            {persona === 'emotional_companion' && <Text style={styles.personaSelected}>선택됨</Text>}
          </View>
          <Text style={styles.personaDescription}>감정을 세심하게 듣고 공감하는 대화 동반자</Text>
        </Pressable>
      </View>

      <Text style={styles.sectionTitle}>대화 스타일</Text>
      <View style={styles.card}>
        <View style={styles.switchRow}>
          <View style={styles.switchCopy}>
            <Text style={styles.rowLabel}>반말 모드</Text>
            <Text style={styles.switchDescription}>
              {casualMode ? '친근하고 자연스러운 반말로 답해요.' : '따뜻한 존댓말로 답해요.'}
            </Text>
          </View>
          <Switch
            accessibilityLabel="반말 모드"
            onValueChange={onCasualModeChange}
            thumbColor="#FFFFFF"
            trackColor={{ false: colors.border, true: colors.primary }}
            value={casualMode}
          />
        </View>
      </View>

      <Text style={styles.sectionTitle}>음성 답변 설정</Text>
      <View style={[styles.card, styles.voiceReplyCard]}>
        <View style={styles.switchRow}>
          <View style={styles.switchCopy}>
            <Text style={styles.rowLabel}>음성으로 바로 답하기</Text>
            <Text style={styles.switchDescription}>
              {voiceReplyEnabled ? '답변이 도착하면 음성을 자동으로 재생해요.' : '음성으로 듣기 버튼을 눌러 재생해요.'}
            </Text>
          </View>
          <Switch
            accessibilityLabel="음성으로 바로 답하기"
            onValueChange={onVoiceReplyChange}
            thumbColor="#FFFFFF"
            trackColor={{ false: colors.border, true: colors.primary }}
            value={voiceReplyEnabled}
          />
        </View>
      </View>
      <View style={[styles.card, styles.disabledVoiceSettings]}>
        <View pointerEvents="none" style={styles.disabledVoiceContent}>
          <ChoiceRow label="톤" options={['차분하게', '자연스럽게', '밝게']} />
          <View style={styles.divider} />
          <ChoiceRow label="말하기 속도" options={['느리게', '보통', '빠르게']} />
        </View>
        <BlurView
          accessibilityLabel="음성 답변 설정 준비 중"
          intensity={18}
          style={styles.comingSoonOverlay}
          tint={darkMode ? 'dark' : 'light'}
        >
          <View style={styles.comingSoonBadge}>
            <Text style={styles.comingSoonIcon}>◇</Text>
            <View>
              <Text style={styles.comingSoonTitle}>준비 중</Text>
              <Text style={styles.comingSoonText}>톤과 말하기 속도 설정을 곧 제공할게요.</Text>
            </View>
          </View>
        </BlurView>
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>개인화 음성</Text>
        <Pressable
          onPress={() => { setShowVoiceForm((value) => !value); setVoiceMessage(''); }}
          style={styles.addVoiceButton}
        >
          <Text style={styles.addVoiceButtonText}>{showVoiceForm ? '닫기' : '+ 음성 추가'}</Text>
        </Pressable>
      </View>

      {showVoiceForm && (
        <View style={[styles.card, styles.voiceForm]}>
          <Text style={styles.formTitle}>내 목소리 등록</Text>
          <Text style={styles.formGuide}>10~20초 정도 조용한 곳에서 또렷하게 녹음하면 더 자연스러운 음성을 만들 수 있어요.</Text>
          <Text style={styles.inputLabel}>음성 이름</Text>
          <TextInput
            maxLength={60}
            onChangeText={setVoiceName}
            placeholder="예: 나의 편안한 목소리"
            placeholderTextColor="#A49DAB"
            style={styles.input}
            value={voiceName}
          />
          <Text style={styles.inputLabel}>참조 문장</Text>
          <TextInput
            maxLength={500}
            multiline
            onChangeText={setReferenceText}
            style={[styles.input, styles.referenceInput]}
            value={referenceText}
          />
          <Text style={styles.inputHint}>녹음할 때 위 문장을 그대로 읽어 주세요.</Text>
          <Text style={styles.inputLabel}>설명 (선택)</Text>
          <TextInput
            maxLength={200}
            onChangeText={setDescription}
            placeholder="예: 차분한 대화용 음성"
            placeholderTextColor="#A49DAB"
            style={styles.input}
            value={description}
          />
          <Pressable
            disabled={saving}
            onPress={() => void toggleSampleRecording()}
            style={[styles.recordButton, recording && styles.recordButtonActive]}
          >
            <Text style={[styles.recordButtonText, recording && styles.recordButtonTextActive]}>
              {recording
                ? `■ 녹음 완료 (${Math.max(1, Math.round(sampleState.durationMillis / 1000))}초)`
                : sampleUri ? '● 다시 녹음하기' : '● 샘플 녹음 시작'}
            </Text>
          </Pressable>
          {!!sampleUri && !recording && <Text style={styles.sampleReady}>✓ 음성 샘플이 준비됐어요.</Text>}
          {!!voiceMessage && <Text style={styles.voiceMessage}>{voiceMessage}</Text>}
          <Pressable
            disabled={saving || recording || !sampleUri}
            onPress={() => void saveVoice()}
            style={[styles.saveVoiceButton, (saving || recording || !sampleUri) && styles.disabledButton]}
          >
            {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.saveVoiceButtonText}>개인화 음성 등록</Text>}
          </Pressable>
        </View>
      )}

      <View style={styles.card}>
        <View style={styles.personalizationStatus}>
          <Text style={styles.personalizationTitle}>
            {voiceStatus?.has_personalized_voice ? '✓ 개인화 음성 사용 가능' : '기본 응답 음성 사용 중'}
          </Text>
          <Text style={styles.personalizationDescription}>
            {voiceStatus?.has_personalized_voice
              ? `이 계정에 등록된 개인화 음성 ${voiceStatus.personalized_voice_count}개`
              : '기본 음성은 모든 계정에 공통으로 제공돼요.'}
          </Text>
        </View>
        {voices.length ? voices.map((voice, index) => (
          <View key={voice.id} style={[styles.voiceRow, index < voices.length - 1 && styles.voiceBorder]}>
            <View style={styles.voiceIcon}><Text style={styles.voiceIconText}>♪</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.voiceName}>{voice.voice_name}</Text>
              <Text numberOfLines={1} style={styles.voiceDesc}>
                {voice.is_default ? '모든 계정에 제공되는 기본 응답 음성' : voice.description || '이 계정에 등록된 개인화 음성'}
              </Text>
            </View>
          </View>
        )) : <Text style={styles.emptyVoice}>등록된 개인화 음성이 없습니다. 위의 음성 추가 버튼으로 만들어 보세요.</Text>}
      </View>

      <Text style={styles.sectionTitle}>계정</Text>
      <Pressable onPress={() => void logout()} style={styles.logout}>
        <Text style={styles.logoutText}>로그아웃</Text>
      </Pressable>
      <Text style={styles.version}>MemoryPal beta · Python 3.12 API</Text>
    </ScrollView>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  root: { padding: 22, paddingBottom: 38 },
  title: { color: colors.ink, fontSize: 29, fontWeight: '900', marginBottom: 20 },
  profileCard: { flexDirection: 'row', alignItems: 'center', gap: 13, backgroundColor: colors.primarySoft, borderRadius: 22, padding: 16 },
  avatar: { width: 48, height: 48, borderRadius: 17, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: '#FFFFFF', fontSize: 19, fontWeight: '900' },
  name: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  email: { color: colors.muted, fontSize: 11, marginTop: 3 },
  sectionTitle: { color: colors.ink, fontSize: 14, fontWeight: '900', marginTop: 25, marginBottom: 10 },
  sectionHeader: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  addVoiceButton: { marginBottom: 7, borderRadius: 999, backgroundColor: colors.primarySoft, paddingHorizontal: 13, paddingVertical: 8 },
  addVoiceButtonText: { color: colors.primaryDark, fontSize: 12, fontWeight: '800' },
  card: { backgroundColor: colors.surface, borderRadius: 20, borderWidth: 1, borderColor: colors.border, padding: 16 },
  personaOption: { borderRadius: 15, padding: 13, borderWidth: 1, borderColor: 'transparent' },
  personaOptionActive: { backgroundColor: colors.primarySoft, borderColor: '#D8C7FA' },
  personaHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  personaTitle: { color: colors.ink, fontSize: 14, fontWeight: '900' },
  personaSelected: { color: colors.primaryDark, fontSize: 10, fontWeight: '900' },
  personaDescription: { color: colors.muted, fontSize: 11, lineHeight: 16, marginTop: 5 },
  disabledVoiceSettings: { position: 'relative', overflow: 'hidden' },
  voiceReplyCard: { marginBottom: 10 },
  disabledVoiceContent: { opacity: 0.5 },
  comingSoonOverlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, alignItems: 'center', justifyContent: 'center', padding: 14 },
  comingSoonBadge: { flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 14, paddingVertical: 11 },
  comingSoonIcon: { color: colors.primary, fontSize: 20, fontWeight: '900' },
  comingSoonTitle: { color: colors.ink, fontSize: 13, fontWeight: '900' },
  comingSoonText: { color: colors.muted, fontSize: 10, marginTop: 3 },
  voiceForm: { marginBottom: 12, borderColor: '#DCCFFC', gap: 9 },
  formTitle: { color: colors.ink, fontSize: 17, fontWeight: '900' },
  formGuide: { color: colors.muted, fontSize: 12, lineHeight: 18, marginBottom: 4 },
  inputLabel: { color: colors.ink, fontSize: 12, fontWeight: '800', marginTop: 5 },
  input: { minHeight: 46, borderWidth: 1, borderColor: colors.border, borderRadius: 13, paddingHorizontal: 13, color: colors.ink, backgroundColor: colors.input, fontSize: 14 },
  referenceInput: { minHeight: 76, paddingTop: 12, paddingBottom: 12, textAlignVertical: 'top' },
  inputHint: { color: colors.muted, fontSize: 10, marginTop: -4 },
  recordButton: { minHeight: 48, marginTop: 5, borderRadius: 14, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  recordButtonActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  recordButtonText: { color: colors.primaryDark, fontSize: 13, fontWeight: '800' },
  recordButtonTextActive: { color: '#FFFFFF' },
  sampleReady: { color: colors.success, fontSize: 11, fontWeight: '700', textAlign: 'center' },
  voiceMessage: { color: colors.primaryDark, fontSize: 11, lineHeight: 16, textAlign: 'center' },
  saveVoiceButton: { minHeight: 50, borderRadius: 14, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  saveVoiceButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '900' },
  disabledButton: { opacity: 0.45 },
  choiceBlock: { gap: 11 },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  switchCopy: { flex: 1, gap: 5 },
  switchDescription: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  rowLabel: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  choiceRow: { flexDirection: 'row', gap: 6 },
  choice: { flex: 1, alignItems: 'center', paddingVertical: 9, borderRadius: 11, backgroundColor: colors.subtle },
  choiceActive: { backgroundColor: colors.primarySoft },
  choiceText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  choiceTextActive: { color: colors.primaryDark },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 17 },
  voiceRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  personalizationStatus: { borderRadius: 14, backgroundColor: colors.primarySoft, padding: 13, marginBottom: 8 },
  personalizationTitle: { color: colors.primaryDark, fontSize: 13, fontWeight: '900' },
  personalizationDescription: { color: colors.muted, fontSize: 11, marginTop: 4 },
  voiceBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  voiceIcon: { width: 39, height: 39, borderRadius: 14, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  voiceIconText: { color: colors.primaryDark, fontSize: 16, fontWeight: '800' },
  voiceName: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  voiceDesc: { color: colors.muted, fontSize: 10, marginTop: 3 },
  emptyVoice: { color: colors.muted, fontSize: 12, textAlign: 'center', paddingVertical: 12 },
  logout: { height: 51, borderRadius: 16, borderWidth: 1, borderColor: colors.danger, backgroundColor: colors.dangerSoft, alignItems: 'center', justifyContent: 'center' },
  logoutText: { color: colors.danger, fontSize: 14, fontWeight: '800' },
  version: { color: '#A49DAB', fontSize: 10, textAlign: 'center', marginTop: 22 },
});
