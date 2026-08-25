import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api, createAIPipelineTrace } from '../api';
import { unlockWebAudio } from '../audioPlayback';
import { RecordingOrb } from '../components/RecordingOrb';
import { useLiveRecorder } from '../hooks/useLiveRecorder';
import { useTheme, type ThemeColors } from '../theme';
import type { ChatResponse, LocalModel, Persona, ReasoningEffort, User, Voice } from '../types';
import { conversationModelChoices } from '../utils/modelChoices';

type Props = {
  token: string;
  user: User;
  casualMode: boolean;
  persona: Persona;
  voiceId?: string;
  voiceReplyEnabled: boolean;
  internetEnabled: boolean;
  thinkingMode: boolean;
  reasoningEffort?: ReasoningEffort;
  modelKey?: string;
  onModelKeyChange: (modelKey: string | undefined) => void;
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

export function HomeScreen({ token, user, casualMode, persona, voiceId, voiceReplyEnabled, internetEnabled, thinkingMode, reasoningEffort, modelKey, onModelKeyChange, onPersonaChange, onVoiceIdChange, onConversation, onVoiceProcessingChange, onOpenAccount, onLogout }: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const recorder = useLiveRecorder(token);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [processing, setProcessing] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const [localModels, setLocalModels] = useState<LocalModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelBusyKey, setModelBusyKey] = useState<string>();
  const [modelError, setModelError] = useState('');
  const [serverModel, setServerModel] = useState<{
    model_key?: string | null; display_name?: string; loaded?: boolean;
  }>();
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
  const activeModelKey = serverModel?.model_key || modelKey || '';
  const activeLocalModel = localModels.find((model) => model.key === activeModelKey);
  const activeModelLabel = serverModel?.display_name
    || activeLocalModel?.display_name
    || activeModelKey
    || 'LM Studio 상태 확인 중';
  const selectableModels = conversationModelChoices(localModels, persona);

  const refreshModels = async () => {
    setModelsLoading(true);
    setModelError('');
    try {
      const response = await api.localModels(token);
      if (mountedRef.current) setLocalModels(Array.isArray(response.models) ? response.models : []);
    } catch (reason) {
      if (mountedRef.current) {
        setModelError(reason instanceof Error ? reason.message : '모델 목록을 불러오지 못했습니다.');
      }
    } finally {
      if (mountedRef.current) setModelsLoading(false);
    }
  };

  const openModelMenu = () => {
    setModelMenuOpen(true);
    void refreshModels();
  };

  const selectModel = async (model: LocalModel) => {
    if (modelBusyKey) return;
    setModelBusyKey(model.key);
    setModelError('');
    try {
      if (!model.loaded_instances?.length) await api.loadModel(token, model.key, 40960);
      if (!mountedRef.current) return;
      if (persona === 'emotional_companion') onPersonaChange('default');
      onModelKeyChange(model.key);
      setModelMenuOpen(false);
      await refreshModels();
    } catch (reason) {
      if (mountedRef.current) {
        const errorMessage = reason instanceof Error ? reason.message : '모델을 선택하지 못했습니다.';
        if (errorMessage.includes('리소스가 부족하여 로드가 제한됩니다.')) {
          Alert.alert('모델 로드 제한', '리소스가 부족하여 로드가 제한됩니다.');
        }
        setModelError(errorMessage);
      }
    } finally {
      if (mountedRef.current) setModelBusyKey(undefined);
    }
  };

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
    let active = true;
    setServerModel(undefined);
    const refreshCurrentModel = () => {
      void api.modelSelection(token, persona).then((current) => {
        if (active) setServerModel(current);
      }).catch(() => {
        if (active) setServerModel(undefined);
      });
    };
    refreshCurrentModel();
    const timer = setInterval(refreshCurrentModel, 30_000);
    return () => { active = false; clearInterval(timer); };
  }, [modelKey, persona, token]);

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
      const pipelineTrace = createAIPipelineTrace([
        'stt', 'llm', ...(voiceReplyEnabled ? ['tts' as const] : []),
      ]);
      const transcript = await recorder.stop(pipelineTrace);
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
        modelKey,
        pipelineTrace,
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
        <Pressable
          accessibilityHint="다운로드된 대화 모델 목록을 엽니다"
          accessibilityLabel={`현재 모델 ${activeModelLabel}`}
          accessibilityRole="button"
          onPress={openModelMenu}
          style={({ pressed }) => [styles.currentModel, pressed && styles.currentModelPressed]}
        >
          <View style={styles.currentModelCopy}>
            <Text style={styles.currentModelCaption}>
              현재 모델 · {serverModel?.loaded ? 'LM Studio 로드됨' : '선택 시 자동 로드'}
            </Text>
            <Text numberOfLines={1} style={styles.currentModelValue}>{activeModelLabel}</Text>
          </View>
          <Text style={styles.currentModelAction}>선택</Text>
        </Pressable>
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
    <Modal animationType="fade" onRequestClose={() => setModelMenuOpen(false)} transparent visible={modelMenuOpen}>
      <Pressable accessibilityLabel="모델 선택 닫기" onPress={() => setModelMenuOpen(false)} style={styles.modelOverlay}>
        <Pressable accessibilityRole="menu" onPress={(event) => event.stopPropagation()} style={styles.modelSheet}>
          <View style={styles.modelSheetHeader}>
            <View style={styles.modelSheetHeaderCopy}>
              <Text style={styles.modelSheetTitle}>대화 모델 선택</Text>
              <Text style={styles.modelSheetDescription}>기본 페르소나에서도 선택한 모델을 그대로 사용합니다.</Text>
            </View>
            <Pressable accessibilityLabel="모델 선택 닫기" onPress={() => setModelMenuOpen(false)} style={styles.modelClose}>
              <Text style={styles.modelCloseText}>×</Text>
            </Pressable>
          </View>
          {modelsLoading && !localModels.length ? (
            <View style={styles.modelLoading}><ActivityIndicator color={colors.primary} /><Text style={styles.modelLoadingText}>모델을 확인하고 있어요…</Text></View>
          ) : (
            <ScrollView style={styles.modelList} showsVerticalScrollIndicator={false}>
              {!selectableModels.length && <Text style={styles.modelEmpty}>선택할 수 있는 기본 대화 모델이 없습니다.</Text>}
              {selectableModels.map((model) => {
                const selected = persona !== 'emotional_companion' && model.key === activeModelKey;
                const loaded = !!model.loaded_instances?.length;
                const busy = modelBusyKey === model.key;
                return (
                  <Pressable
                    accessibilityRole="menuitem"
                    disabled={!!modelBusyKey}
                    key={model.key}
                    onPress={() => void selectModel(model)}
                    style={({ pressed }) => [styles.modelOption, selected && styles.modelOptionSelected, pressed && styles.modelOptionPressed]}
                  >
                    <View style={styles.modelOptionCopy}>
                      <Text numberOfLines={1} style={[styles.modelOptionTitle, selected && styles.modelOptionTitleSelected]}>{model.display_name || model.key}</Text>
                      <Text numberOfLines={1} style={styles.modelOptionDetail}>{loaded ? '로드됨 · 바로 선택 가능' : '로드 후 선택 가능'}</Text>
                    </View>
                    {busy ? <ActivityIndicator color={colors.primary} /> : <Text style={[styles.modelOptionState, selected && styles.modelOptionStateSelected]}>{selected ? '사용 중' : loaded ? '선택' : '로드'}</Text>}
                  </Pressable>
                );
              })}
            </ScrollView>
          )}
          {!!modelError && <Text style={styles.modelError}>{modelError}</Text>}
          <Text style={styles.modelHint}>모델 다운로드와 로드는 설정 › 직접 모델 관리에서 할 수 있습니다.</Text>
        </Pressable>
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
  currentModel: { width: '100%', maxWidth: 330, minHeight: 58, marginTop: -22, marginBottom: 13, paddingHorizontal: 15, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', gap: 9, borderRadius: 17, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, shadowColor: '#251832', shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.1, shadowRadius: 13, elevation: 4 },
  currentModelPressed: { borderColor: colors.primary, transform: [{ scale: 0.99 }] },
  currentModelCopy: { flex: 1, minWidth: 0 },
  currentModelCaption: { color: colors.muted, fontSize: 10, fontWeight: '800', marginBottom: 3 },
  currentModelValue: { color: colors.ink, fontSize: 13, fontWeight: '900' },
  currentModelAction: { color: colors.primaryDark, fontSize: 11, fontWeight: '900' },
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
  dropdownMenu: { marginTop: 6, zIndex: 40, elevation: 12, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 5, shadowColor: '#2E2438', shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.16, shadowRadius: 14 },
  dropdownScroll: { maxHeight: 220 },
  dropdownOption: { minHeight: 48, justifyContent: 'center', borderRadius: 11, paddingHorizontal: 10, paddingVertical: 7 },
  dropdownOptionActive: { backgroundColor: colors.primarySoft },
  dropdownOptionText: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  dropdownOptionTextActive: { color: colors.primaryDark, fontWeight: '900' },
  dropdownOptionDetail: { color: colors.muted, fontSize: 9, marginTop: 3 },
  modelOverlay: { flex: 1, justifyContent: 'flex-end', alignItems: 'center', backgroundColor: 'rgba(16, 11, 23, 0.58)' },
  modelSheet: { width: '100%', maxWidth: 560, maxHeight: '72%', gap: 14, borderTopLeftRadius: 26, borderTopRightRadius: 26, borderWidth: 1, borderBottomWidth: 0, borderColor: colors.border, backgroundColor: colors.surface, padding: 20, paddingBottom: 26 },
  modelSheetHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  modelSheetHeaderCopy: { flex: 1 },
  modelSheetTitle: { color: colors.ink, fontSize: 19, fontWeight: '900' },
  modelSheetDescription: { color: colors.muted, fontSize: 11, lineHeight: 17, marginTop: 4 },
  modelClose: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: colors.subtle },
  modelCloseText: { color: colors.ink, fontSize: 23, lineHeight: 25 },
  modelLoading: { minHeight: 120, alignItems: 'center', justifyContent: 'center', gap: 10 },
  modelLoadingText: { color: colors.muted, fontSize: 12 },
  modelList: { maxHeight: 360 },
  modelEmpty: { color: colors.muted, fontSize: 13, lineHeight: 21, textAlign: 'center', paddingHorizontal: 20, paddingVertical: 32 },
  modelOption: { minHeight: 68, marginBottom: 9, paddingHorizontal: 14, paddingVertical: 11, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background },
  modelOptionSelected: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  modelOptionPressed: { opacity: 0.76 },
  modelOptionCopy: { flex: 1, minWidth: 0 },
  modelOptionTitle: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  modelOptionTitleSelected: { color: colors.primaryDark },
  modelOptionDetail: { color: colors.muted, fontSize: 10, marginTop: 5 },
  modelOptionState: { color: colors.primaryDark, fontSize: 11, fontWeight: '900' },
  modelOptionStateSelected: { color: colors.primary },
  modelError: { color: colors.danger, fontSize: 11, lineHeight: 17, paddingHorizontal: 2 },
  modelHint: { color: colors.muted, fontSize: 10, lineHeight: 16, textAlign: 'center' },
});
