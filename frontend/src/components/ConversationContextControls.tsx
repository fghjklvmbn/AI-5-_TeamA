import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { api } from '../api';
import { useTheme, type ThemeColors } from '../theme';
import type { LocalModel, Persona, Voice } from '../types';
import { conversationModelChoices } from '../utils/modelChoices';

type Menu = 'persona' | 'model' | 'voice';

type Props = {
  token: string;
  persona: Persona;
  modelKey?: string;
  voiceId?: string;
  compact?: boolean;
  disabled?: boolean;
  onPersonaChange: (persona: Persona) => void | Promise<void>;
  onModelKeyChange: (modelKey: string | undefined) => void | Promise<void>;
  onVoiceIdChange: (voiceId: string | undefined) => void;
};

const PERSONAS: Array<{ id: Persona; label: string; detail: string }> = [
  { id: 'default', label: '기본', detail: '정확하고 실용적인 일반 AI 도우미' },
  { id: 'emotional_companion', label: '정서적 동반자', detail: '감정을 세심하게 듣고 공감하는 대화 동반자' },
  { id: 'none', label: '없음', detail: '역할 설정 없이 기억과 검색 근거로 대화' },
];

function modelLabel(model?: Pick<LocalModel, 'key' | 'display_name'>): string {
  return model?.display_name || model?.key || '모델 확인 중';
}

export function ConversationContextControls({
  token,
  persona,
  modelKey,
  voiceId,
  compact = false,
  disabled = false,
  onPersonaChange,
  onModelKeyChange,
  onVoiceIdChange,
}: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors, compact);
  const [expanded, setExpanded] = useState(false);
  const [menu, setMenu] = useState<Menu>();
  const [models, setModels] = useState<LocalModel[]>([]);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [serverModel, setServerModel] = useState<{ model_key?: string | null; display_name?: string }>();
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingVoices, setLoadingVoices] = useState(false);
  const [busyKey, setBusyKey] = useState<string>();
  const [error, setError] = useState('');
  const mountedRef = useRef(true);

  const activePersona = PERSONAS.find((option) => option.id === persona) ?? PERSONAS[0]!;
  const activeModel = models.find((model) => model.key === (serverModel?.model_key || modelKey));
  const activeModelLabel = serverModel?.display_name
    || activeModel?.display_name
    || activeModel?.key
    || modelKey
    || '모델 확인 중';
  const activeVoice = voices.find((voice) => voice.id === voiceId)
    || voices.find((voice) => voice.is_default);
  const activeVoiceLabel = activeVoice?.voice_name || (voiceId ? '선택된 음성' : '기본 음성');
  const selectableModels = conversationModelChoices(models, persona);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setServerModel(undefined);
    void api.modelSelection(token, persona, controller.signal).then((selection) => {
      if (!controller.signal.aborted) setServerModel(selection);
    }).catch(() => undefined);
    return () => controller.abort();
  }, [modelKey, persona, token]);

  useEffect(() => {
    let active = true;
    void api.voices(token).then((response) => {
      if (active) setVoices(Array.isArray(response) ? response : []);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [token]);

  const openMenu = async (nextMenu: Menu) => {
    if (disabled || busyKey) return;
    setError('');
    setMenu(nextMenu);
    if (nextMenu === 'persona') return;
    if (nextMenu === 'voice') {
      setLoadingVoices(true);
      try {
        const response = await api.voices(token);
        if (mountedRef.current) setVoices(Array.isArray(response) ? response : []);
      } catch (reason) {
        if (mountedRef.current) {
          setError(reason instanceof Error ? reason.message : '응답 음성을 불러오지 못했어요.');
        }
      } finally {
        if (mountedRef.current) setLoadingVoices(false);
      }
      return;
    }
    setLoadingModels(true);
    try {
      const response = await api.localModels(token);
      if (mountedRef.current) setModels(Array.isArray(response.models) ? response.models : []);
    } catch (reason) {
      if (mountedRef.current) {
        setError(reason instanceof Error ? reason.message : '다운로드된 모델을 불러오지 못했어요.');
      }
    } finally {
      if (mountedRef.current) setLoadingModels(false);
    }
  };

  const selectPersona = async (nextPersona: Persona) => {
    if (busyKey || nextPersona === persona) {
      setMenu(undefined);
      return;
    }
    setBusyKey(`persona:${nextPersona}`);
    setError('');
    try {
      await onPersonaChange(nextPersona);
      if (mountedRef.current) setMenu(undefined);
    } catch (reason) {
      if (mountedRef.current) {
        setError(reason instanceof Error ? reason.message : '페르소나를 변경하지 못했어요.');
      }
    } finally {
      if (mountedRef.current) setBusyKey(undefined);
    }
  };

  const selectModel = async (model: LocalModel) => {
    if (busyKey || model.processing) return;
    setBusyKey(`model:${model.key}`);
    setError('');
    try {
      if (!model.loaded_instances?.length) await api.loadModel(token, model.key, 40960);
      if (persona === 'emotional_companion') await onPersonaChange('default');
      await onModelKeyChange(model.key);
      if (mountedRef.current) {
        setServerModel({ model_key: model.key, display_name: model.display_name });
        setMenu(undefined);
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : '모델을 불러오지 못했어요.';
      if (message.includes('리소스가 부족하여 로드가 제한됩니다.')) {
        Alert.alert('모델 로드 제한', '리소스가 부족하여 로드가 제한됩니다.');
      }
      if (mountedRef.current) setError(message);
    } finally {
      if (mountedRef.current) setBusyKey(undefined);
    }
  };

  const selectVoice = (voice: Voice) => {
    if (busyKey) return;
    if (voice.id === voiceId) {
      setMenu(undefined);
      return;
    }
    onVoiceIdChange(voice.id);
    setMenu(undefined);
  };

  return <>
    <View style={styles.summaryBar}>
      <Text numberOfLines={1} style={styles.summaryText}>
        {expanded ? '페르소나 · 모델 · 응답 음성' : `${activePersona.label} · ${activeModelLabel}`}
      </Text>
      <Pressable
        accessibilityLabel={expanded ? '대화 상세 설정 닫기' : '대화 상세 설정 열기'}
        accessibilityState={{ expanded }}
        onPress={() => setExpanded((current) => !current)}
        style={[styles.summaryButton, expanded && styles.summaryButtonActive]}
      >
        <Text style={[styles.summaryButtonText, expanded && styles.summaryButtonTextActive]}>
          ⚙ {expanded ? '설정 닫기' : '상세 설정'}
        </Text>
      </Pressable>
    </View>
    {expanded && <View style={styles.bar}>
      <Pressable
        accessibilityLabel={`페르소나 선택, 현재 ${activePersona.label}`}
        disabled={disabled || !!busyKey}
        onPress={() => void openMenu('persona')}
        style={[styles.control, (disabled || !!busyKey) && styles.disabled]}
      >
        <Text style={styles.controlLabel}>페르소나</Text>
        <Text numberOfLines={1} style={styles.controlValue}>{activePersona.label}</Text>
      </Pressable>
      <Pressable
        accessibilityLabel={`모델 선택, 현재 ${activeModelLabel}`}
        disabled={disabled || !!busyKey}
        onPress={() => void openMenu('model')}
        style={[styles.control, (disabled || !!busyKey) && styles.disabled]}
      >
        <Text style={styles.controlLabel}>모델</Text>
        <View style={styles.modelValueRow}>
          {!!busyKey?.startsWith('model:') && <ActivityIndicator color={colors.primary} size="small" />}
          <Text numberOfLines={1} style={styles.controlValue}>{activeModelLabel}</Text>
        </View>
      </Pressable>
      <Pressable
        accessibilityLabel={`응답 음성 선택, 현재 ${activeVoiceLabel}`}
        disabled={disabled || !!busyKey}
        onPress={() => void openMenu('voice')}
        style={[styles.control, (disabled || !!busyKey) && styles.disabled]}
      >
        <Text style={styles.controlLabel}>응답 음성</Text>
        <Text numberOfLines={1} style={styles.controlValue}>{activeVoiceLabel}</Text>
      </Pressable>
    </View>}

    <Modal animationType="fade" onRequestClose={() => !busyKey && setMenu(undefined)} transparent visible={!!menu}>
      <Pressable onPress={() => !busyKey && setMenu(undefined)} style={styles.backdrop}>
        <Pressable onPress={() => undefined} style={styles.sheet}>
          <View style={styles.handle} />
          <Text style={styles.sheetTitle}>
            {menu === 'persona' ? '페르소나 선택' : menu === 'model' ? '대화 모델 선택' : '응답 음성 선택'}
          </Text>
          <Text style={styles.sheetDescription}>
            {menu === 'persona'
              ? '대화의 역할과 말투를 바로 변경합니다.'
              : menu === 'voice'
                ? '답변을 읽어줄 기본 음성 또는 개인화 음성을 선택합니다.'
                : persona === 'emotional_companion'
                  ? '모델을 직접 선택하면 페르소나는 기본으로 전환됩니다.'
                  : '다운로드된 LLM을 선택하며, 필요한 경우 자동으로 로드합니다.'}
          </Text>
          {!!error && <Text style={styles.error}>{error}</Text>}

          {menu === 'persona' ? <View style={styles.options}>
            {PERSONAS.map((option) => {
              const selected = option.id === persona;
              const loading = busyKey === `persona:${option.id}`;
              return <Pressable
                accessibilityLabel={`${option.label} 페르소나`}
                accessibilityState={{ selected, disabled: !!busyKey }}
                disabled={!!busyKey}
                key={option.id}
                onPress={() => void selectPersona(option.id)}
                style={[styles.option, selected && styles.optionActive]}
              >
                <View style={styles.optionTextWrap}>
                  <Text style={[styles.optionTitle, selected && styles.optionTitleActive]}>{option.label}</Text>
                  <Text style={styles.optionDetail}>{option.detail}</Text>
                </View>
                {loading
                  ? <ActivityIndicator color={colors.primary} />
                  : selected && <Text style={styles.selectedBadge}>선택됨</Text>}
              </Pressable>;
            })}
          </View> : menu === 'voice' ? loadingVoices ? (
            <View style={styles.loading}><ActivityIndicator color={colors.primary} /><Text style={styles.loadingText}>응답 음성을 불러오고 있어요.</Text></View>
          ) : <ScrollView contentContainerStyle={styles.options} style={styles.modelList}>
            {!voices.length && <Text style={styles.emptyText}>선택할 수 있는 응답 음성이 없습니다.</Text>}
            {voices.map((voice) => {
              const selected = voice.id === (activeVoice?.id || voiceId);
              return <Pressable
                accessibilityLabel={`${voice.voice_name} 응답 음성 선택`}
                accessibilityState={{ selected, disabled: !!busyKey }}
                disabled={!!busyKey}
                key={voice.id}
                onPress={() => selectVoice(voice)}
                style={[styles.option, selected && styles.optionActive]}
              >
                <View style={styles.optionTextWrap}>
                  <Text numberOfLines={1} style={[styles.optionTitle, selected && styles.optionTitleActive]}>{voice.voice_name}</Text>
                  <Text style={styles.optionDetail}>{voice.is_default ? '공용 기본 음성' : '개인화 음성'}</Text>
                </View>
                {selected && <Text style={styles.selectedBadge}>선택됨</Text>}
              </Pressable>;
            })}
          </ScrollView> : loadingModels ? (
            <View style={styles.loading}><ActivityIndicator color={colors.primary} /><Text style={styles.loadingText}>모델 목록을 불러오고 있어요.</Text></View>
          ) : <ScrollView contentContainerStyle={styles.options} style={styles.modelList}>
            {!selectableModels.length && <Text style={styles.emptyText}>선택할 수 있는 기본 대화 모델이 없습니다.</Text>}
            {selectableModels.map((model) => {
              const selected = model.key === (serverModel?.model_key || modelKey);
              const loading = busyKey === `model:${model.key}`;
              const unavailable = !!busyKey || !!model.processing;
              return <Pressable
                accessibilityLabel={`${modelLabel(model)} 모델 선택`}
                accessibilityState={{ selected, disabled: unavailable }}
                disabled={unavailable}
                key={model.key}
                onPress={() => void selectModel(model)}
                style={[styles.option, selected && styles.optionActive, unavailable && styles.disabled]}
              >
                <View style={styles.optionTextWrap}>
                  <Text numberOfLines={1} style={[styles.optionTitle, selected && styles.optionTitleActive]}>{modelLabel(model)}</Text>
                  <Text style={styles.optionDetail}>
                    {model.processing ? '응답 처리 중' : model.loaded_instances?.length ? '로드됨' : '선택 시 자동 로드'}
                  </Text>
                </View>
                {loading
                  ? <ActivityIndicator color={colors.primary} />
                  : selected && <Text style={styles.selectedBadge}>현재 모델</Text>}
              </Pressable>;
            })}
          </ScrollView>}
        </Pressable>
      </Pressable>
    </Modal>
  </>;
}

const createStyles = (colors: ThemeColors, compact: boolean) => StyleSheet.create({
  summaryBar: { minHeight: compact ? 38 : 42, flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: compact ? 9 : 14, paddingVertical: 5, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: colors.surface },
  summaryText: { flex: 1, minWidth: 0, color: colors.muted, fontSize: compact ? 9 : 10, fontWeight: '700' },
  summaryButton: { minHeight: 28, alignItems: 'center', justifyContent: 'center', borderRadius: 10, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.input, paddingHorizontal: 10 },
  summaryButtonActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  summaryButtonText: { color: colors.muted, fontSize: 10, fontWeight: '900' },
  summaryButtonTextActive: { color: colors.primaryDark },
  bar: { flexDirection: 'row', gap: 8, paddingHorizontal: compact ? 9 : 14, paddingTop: compact ? 2 : 4, paddingBottom: compact ? 7 : 9, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: colors.surface },
  control: { flex: 1, minWidth: 0, minHeight: compact ? 43 : 47, justifyContent: 'center', borderRadius: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.input, paddingHorizontal: compact ? 10 : 12, paddingVertical: 6 },
  controlLabel: { color: colors.muted, fontSize: 9, fontWeight: '800', marginBottom: 2 },
  controlValue: { flexShrink: 1, color: colors.ink, fontSize: compact ? 11 : 12, fontWeight: '900' },
  modelValueRow: { minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 6 },
  disabled: { opacity: 0.45 },
  backdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: colors.overlay },
  sheet: { maxHeight: '76%', minHeight: 300, borderTopLeftRadius: 28, borderTopRightRadius: 28, backgroundColor: colors.surface, padding: 20 },
  handle: { width: 42, height: 4, alignSelf: 'center', borderRadius: 99, backgroundColor: colors.border, marginBottom: 18 },
  sheetTitle: { color: colors.ink, fontSize: 21, fontWeight: '900' },
  sheetDescription: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: 6, marginBottom: 14 },
  error: { color: colors.danger, backgroundColor: colors.dangerSoft, borderRadius: 12, padding: 10, fontSize: 11, marginBottom: 10 },
  options: { gap: 8, paddingBottom: 12 },
  modelList: { flexGrow: 0 },
  option: { minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.input, paddingHorizontal: 14, paddingVertical: 11 },
  optionActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  optionTextWrap: { flex: 1, minWidth: 0 },
  optionTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  optionTitleActive: { color: colors.primaryDark },
  optionDetail: { color: colors.muted, fontSize: 10, lineHeight: 15, marginTop: 4 },
  selectedBadge: { color: colors.primaryDark, fontSize: 10, fontWeight: '900' },
  loading: { minHeight: 150, alignItems: 'center', justifyContent: 'center', gap: 10 },
  loadingText: { color: colors.muted, fontSize: 11 },
  emptyText: { color: colors.muted, textAlign: 'center', paddingVertical: 32, fontSize: 12 },
});
