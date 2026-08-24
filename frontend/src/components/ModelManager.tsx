import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { api } from '../api';
import { useTheme, type ThemeColors } from '../theme';
import type { HuggingFaceModel, LocalModel, ModelDownloadJob, ModelManagerStatus } from '../types';

type Props = {
  token: string;
  selectedModelKey?: string;
  onSelectedModelKeyChange: (modelKey: string | undefined) => void;
};

const DONE = new Set(['completed', 'complete', 'downloaded', 'failed', 'cancelled', 'canceled']);

function readableBytes(value?: number): string {
  if (!value || value < 1) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / (1024 ** index)).toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}

function modelInstances(model: LocalModel) {
  return Array.isArray(model.loaded_instances) ? model.loaded_instances : [];
}

function modelQuantization(model: LocalModel): string {
  if (typeof model.quantization === 'string') return model.quantization;
  return model.quantization?.name || '';
}

function downloadModelName(model?: string): string {
  if (!model) return '모델 정보 확인 중';
  const normalized = model.replace(/\/$/, '');
  return normalized.split('/').pop() || normalized;
}

export function ModelManager({ token, selectedModelKey, onSelectedModelKeyChange }: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const [status, setStatus] = useState<ModelManagerStatus>();
  const [models, setModels] = useState<LocalModel[]>([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<HuggingFaceModel[]>([]);
  const [quantization, setQuantization] = useState('Q4_K_M');
  const [jobs, setJobs] = useState<Record<string, ModelDownloadJob>>({});
  const [busyKey, setBusyKey] = useState<string>();
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [quota, setQuota] = useState({ used: 0, total: 10 * 1024 ** 3 });
  const mounted = useRef(true);
  const modelLoadInProgress = busyKey?.startsWith('load:') === true;
  const visibleDownloadJobs = Object.entries(jobs).filter(([, job]) => ![
    'completed', 'complete', 'downloaded', 'already_downloaded',
  ].includes((job.status ?? '').toLowerCase()));

  const refresh = useCallback(async (signal?: AbortSignal) => {
    const [statusResult, modelsResult, jobsResult] = await Promise.allSettled([
      api.modelManagerStatus(token, signal),
      api.localModels(token, signal),
      api.modelDownloads(token, signal),
    ]);
    if (signal?.aborted || !mounted.current) return;
    if (statusResult.status === 'fulfilled') setStatus(statusResult.value);
    if (modelsResult.status === 'fulfilled') {
      setModels(Array.isArray(modelsResult.value.models) ? modelsResult.value.models : []);
    } else {
      setModels([]);
    }
    if (jobsResult.status === 'fulfilled') {
      setJobs(Object.fromEntries(jobsResult.value.jobs.map((job) => [job.job_id, job])));
      setQuota({ used: jobsResult.value.used_bytes, total: jobsResult.value.quota_bytes });
    }
    if (statusResult.status === 'rejected' && modelsResult.status === 'rejected') {
      throw statusResult.reason;
    }
  }, [token]);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void refresh(controller.signal).catch((reason) => {
      if (!controller.signal.aborted) setMessage(reason instanceof Error ? reason.message : 'LM Studio 상태를 확인하지 못했습니다.');
    });
    const timer = setInterval(() => void refresh(controller.signal).catch(() => undefined), 30000);
    return () => { mounted.current = false; controller.abort(); clearInterval(timer); };
  }, [refresh]);

  useEffect(() => {
    if (!models.length || !selectedModelKey) return;
    if (models.some((model) => model.key === selectedModelKey)) return;
    const fallback = models.find((model) => model.key.toLowerCase().includes('qwen3.5-4b'));
    onSelectedModelKeyChange(fallback?.key);
  }, [models, onSelectedModelKeyChange, selectedModelKey]);

  useEffect(() => {
    const active = Object.entries(jobs).filter(([, job]) => !DONE.has((job.status ?? '').toLowerCase()));
    if (!active.length) return;
    const controller = new AbortController();
    const poll = async () => {
      const updates = await Promise.all(active.map(async ([jobId, previous]) => {
        try {
          const status = await api.modelDownloadStatus(token, jobId, controller.signal);
          return [jobId, { ...previous, ...status, model: status.model || previous.model }] as const;
        } catch (reason) {
          return [jobId, { ...previous, error: reason instanceof Error ? reason.message : '진행 상태 확인 실패' }] as const;
        }
      }));
      if (controller.signal.aborted) return;
      setJobs((current) => ({ ...current, ...Object.fromEntries(updates) }));
      if (updates.some(([, job]) => DONE.has((job.status ?? '').toLowerCase()))) {
        void refresh().catch(() => undefined);
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 1000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [jobs, refresh, token]);

  const search = async () => {
    if (query.trim().length < 2 || searching) return;
    setSearching(true); setMessage('');
    try {
      const response = await api.searchModels(token, query.trim());
      setResults(response.models);
      if (!response.models.length) setMessage('GGUF 모델 검색 결과가 없습니다.');
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : '모델을 검색하지 못했습니다.');
    } finally { setSearching(false); }
  };

  const download = async (model: HuggingFaceModel) => {
    setBusyKey(`download:${model.id}`); setMessage('');
    try {
      const job = await api.downloadModel(token, model.url, quantization.trim() || undefined);
      if (!job.job_id) throw new Error('LM Studio가 다운로드 작업 ID를 반환하지 않았습니다.');
      setJobs((current) => ({ ...current, [job.job_id]: { ...job, model: model.id } }));
      setMessage(`${model.id} 다운로드를 시작했습니다.`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : '다운로드를 시작하지 못했습니다.');
    } finally { setBusyKey(undefined); }
  };

  const dismissFailedDownload = async (jobId: string) => {
    setBusyKey(`dismiss:${jobId}`); setMessage('');
    try {
      await api.dismissModelDownload(token, jobId);
      setJobs((current) => {
        const next = { ...current };
        delete next[jobId];
        return next;
      });
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : '실패한 다운로드를 닫지 못했습니다.');
    } finally { setBusyKey(undefined); }
  };

  const load = async (model: LocalModel) => {
    setBusyKey(`load:${model.key}`); setMessage('');
    try {
      await api.loadModel(token, model.key, 40960);
      onSelectedModelKeyChange(model.key);
      await refresh();
      setMessage(`${model.display_name || model.key} 모델을 40K 컨텍스트로 로드하고 선택했습니다.`);
    } catch (reason) {
      const errorMessage = reason instanceof Error ? reason.message : '모델을 로드하지 못했습니다.';
      if (errorMessage.includes('리소스가 부족하여 로드가 제한됩니다.')) {
        Alert.alert('모델 로드 제한', '리소스가 부족하여 로드가 제한됩니다.');
      }
      setMessage(errorMessage);
    } finally { setBusyKey(undefined); }
  };

  const unload = async (model: LocalModel) => {
    const instance = modelInstances(model)[0];
    if (!instance) return;
    setBusyKey(`unload:${model.key}`); setMessage('');
    try {
      await api.unloadModel(token, instance.id);
      if (selectedModelKey === model.key) onSelectedModelKeyChange(undefined);
      await refresh();
      setMessage(`${model.display_name || model.key} 모델을 언로드했습니다.`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : '모델을 언로드하지 못했습니다.');
    } finally { setBusyKey(undefined); }
  };

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <View style={[styles.dot, status?.server_online ? styles.online : styles.offline]} />
        <View style={styles.headingCopy}>
          <Text style={styles.title}>직접 모델 관리</Text>
          <Text style={styles.muted}>{status?.server_online ? `LM Studio 연결됨 · ${status.model_count}개 모델` : 'LM Studio 연결 확인 중'}</Text>
        </View>
        {!status && <ActivityIndicator color={colors.primary} />}
        <Pressable
          accessibilityLabel={expanded ? '직접 모델 관리 상세 접기' : '직접 모델 관리 상세 펼치기'}
          accessibilityRole="button"
          accessibilityState={{ expanded }}
          onPress={() => setExpanded((value) => !value)}
          style={({ pressed }) => [styles.headerIconButton, pressed && styles.expandTogglePressed]}
        >
          <Image
            source={require('../../assets/model-list.png')}
            style={[styles.headerIcon, { tintColor: expanded ? colors.primary : colors.muted }]}
          />
        </Pressable>
      </View>

      <Text style={styles.muted}>추가 모델 용량 {readableBytes(quota.used)} / {readableBytes(quota.total)}</Text>
      {status?.gpu_metrics_available && <View style={styles.vramSummary}>
        <View style={styles.vramHeader}>
          <Text style={styles.vramLabel}>LLM 서버 사용 가능 VRAM</Text>
          <Text style={styles.vramValue}>{readableBytes(status.vram_free_bytes)} / {readableBytes(status.vram_total_bytes)}</Text>
        </View>
        <View style={styles.vramTrack}>
          <View style={[styles.vramFill, { width: `${Math.min(100, Math.max(0, ((status.vram_used_bytes || 0) / Math.max(1, status.vram_total_bytes || 1)) * 100))}%` }]} />
        </View>
        {!!status.gpu_name && <Text numberOfLines={1} style={styles.vramDevice}>{status.gpu_name}</Text>}
      </View>}

      {!!selectedModelKey && <View style={styles.selected}><Text style={styles.selectedLabel}>현재 대화 모델</Text><Text numberOfLines={1} style={styles.selectedValue}>{selectedModelKey}</Text></View>}

      <Text style={styles.label}>다운로드 상황</Text>
      {!visibleDownloadJobs.length && <Text style={styles.emptyDownload}>진행 중이거나 실패한 다운로드가 없습니다.</Text>}
      {visibleDownloadJobs.map(([jobId, job]) => {
        const total = job.total_size_bytes || 0;
        const progress = total ? Math.min(100, Math.round(((job.downloaded_bytes || 0) / total) * 100)) : 0;
        const failed = (job.status ?? '').toLowerCase() === 'failed';
        return <View key={jobId} style={styles.job}>
          <View style={styles.jobHeader}>
            <Text numberOfLines={1} style={styles.cardTitle}>{downloadModelName(job.model)}</Text>
            {failed && <Pressable
              accessibilityLabel="실패한 다운로드 닫기"
              disabled={!!busyKey}
              onPress={() => void dismissFailedDownload(jobId)}
              style={({ pressed }) => [styles.dismissButton, pressed && styles.dismissButtonPressed, !!busyKey && styles.disabled]}
            ><Text style={styles.dismissText}>×</Text></Pressable>}
          </View>
          <View style={styles.track}><View style={[styles.fill, { width: `${progress}%` }]} /></View>
          <Text style={styles.muted}>{progress}% · {readableBytes(job.downloaded_bytes)} / {readableBytes(total)} · {readableBytes(job.bytes_per_second)}/s · {job.status || '대기 중'}</Text>
          {!!job.error && <Text style={styles.error}>{job.error}</Text>}
          {failed && !!job.model && <Pressable disabled={!!busyKey} onPress={() => void download({ id: job.model!, author: '', downloads: 0, likes: 0, tags: [], url: `https://huggingface.co/${job.model}` })} style={[styles.secondaryButton, !!busyKey && styles.disabled]}><Text style={styles.secondaryText}>재시도</Text></Pressable>}
        </View>;
      })}

      {expanded && <>

      {!!status?.error && <Text style={styles.error}>{status.error}</Text>}
      {!!message && <Text style={styles.message}>{message}</Text>}

      <Text style={styles.label}>Hugging Face GGUF 검색</Text>
      <View style={styles.searchRow}>
        <TextInput value={query} onChangeText={setQuery} onSubmitEditing={() => void search()} placeholder="모델 이름 또는 제작자" placeholderTextColor={colors.muted} style={styles.input} />
        <Pressable disabled={searching} onPress={() => void search()} style={[styles.primaryButton, searching && styles.disabled]}>
          {searching ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>검색</Text>}
        </Pressable>
      </View>

      {results.map((model) => (
        <View key={model.id} style={styles.card}>
          <Text numberOfLines={2} style={styles.cardTitle}>{model.id}</Text>
          <Text style={styles.muted}>{model.parameter_billions}B · 다운로드 {model.downloads.toLocaleString()} · 좋아요 {model.likes.toLocaleString()}</Text>
          <Pressable disabled={!!busyKey || !status?.server_online} onPress={() => void download(model)} style={[styles.secondaryButton, (!!busyKey || !status?.server_online) && styles.disabled]}>
            <Text style={styles.secondaryText}>{busyKey === `download:${model.id}` ? '요청 중…' : '다운로드'}</Text>
          </Pressable>
        </View>
      ))}

      <Text style={styles.label}>다운로드된 모델</Text>
      {!models.length && <Text style={styles.muted}>LM Studio에 다운로드된 모델이 없습니다.</Text>}
      {models.map((model) => {
        const loaded = modelInstances(model).length > 0;
        const selected = selectedModelKey === model.key;
        const quantization = modelQuantization(model);
        const loadingThisModel = busyKey === `load:${model.key}`;
        return <View
          accessibilityState={{ disabled: modelLoadInProgress }}
          key={model.key}
          style={[styles.card, selected && styles.cardSelected, modelLoadInProgress && styles.modelCardDisabled]}
        >
          <View style={styles.modelTitleRow}><Text numberOfLines={1} style={styles.cardTitle}>{model.display_name || model.key}</Text>{model.processing ? <Text style={styles.processingBadge}>처리중</Text> : loaded && <Text style={styles.badge}>로드됨</Text>}</View>
          <Text numberOfLines={1} style={styles.muted}>{model.key}{quantization ? ` · ${quantization}` : ''}{model.size_bytes ? ` · ${readableBytes(model.size_bytes)}` : ''}</Text>
          <View style={styles.actionRow}>
            {loaded ? <>
              <Pressable disabled={!!busyKey || selected} onPress={() => onSelectedModelKeyChange(model.key)} style={[styles.primaryButton, (!!busyKey || selected) && styles.disabled]}><Text style={styles.primaryText}>{selected ? '선택됨' : '대화에 선택'}</Text></Pressable>
              <Pressable
                accessibilityLabel={`${model.display_name || model.key} ${model.processing ? '처리중' : '언로드'}`}
                accessibilityRole="button"
                disabled={!!busyKey || model.processing}
                onPress={() => void unload(model)}
                style={[styles.secondaryButton, (!!busyKey || model.processing) && styles.disabled]}
              ><Text style={styles.secondaryText}>{model.processing ? '처리중' : '언로드'}</Text></Pressable>
            </> : <Pressable
              accessibilityLabel={loadingThisModel ? `${model.display_name || model.key} 로드중` : `${model.display_name || model.key} 로드`}
              disabled={!!busyKey || !status?.server_online}
              onPress={() => void load(model)}
              style={[styles.primaryButton, (!!busyKey || !status?.server_online) && styles.disabled]}
            >
              {loadingThisModel ? <View style={styles.loadingButtonContent}>
                <ActivityIndicator color="#fff" size="small" />
                <Text style={styles.primaryText}>로드중</Text>
              </View> : <Text style={styles.primaryText}>로드</Text>}
            </Pressable>}
          </View>
        </View>;
      })}
      </>}
    </View>
  );
}

function createStyles(colors: ThemeColors) {
  return StyleSheet.create({
    section: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: 12, padding: 18 },
    headingRow: { alignItems: 'center', flexDirection: 'row', gap: 10 }, headingCopy: { flex: 1 },
    dot: { borderRadius: 6, height: 12, width: 12 }, online: { backgroundColor: '#34c786' }, offline: { backgroundColor: '#ef6b73' },
    title: { color: colors.ink, fontSize: 18, fontWeight: '800' }, muted: { color: colors.muted, fontSize: 12, lineHeight: 18 },
    label: { color: colors.ink, fontSize: 14, fontWeight: '800', marginTop: 4 }, smallLabel: { color: colors.muted, fontSize: 12 },
    selected: { backgroundColor: colors.primarySoft, borderRadius: 12, padding: 12 }, selectedLabel: { color: colors.primary, fontSize: 11, fontWeight: '700' }, selectedValue: { color: colors.ink, fontSize: 13, fontWeight: '700', marginTop: 3 },
    vramSummary: { backgroundColor: colors.background, borderRadius: 12, gap: 7, padding: 12 }, vramHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', gap: 10 }, vramLabel: { color: colors.ink, fontSize: 12, fontWeight: '800' }, vramValue: { color: colors.primaryDark, fontSize: 12, fontWeight: '900' }, vramTrack: { backgroundColor: colors.border, borderRadius: 4, height: 7, overflow: 'hidden' }, vramFill: { backgroundColor: colors.primary, borderRadius: 4, height: 7 }, vramDevice: { color: colors.muted, fontSize: 10 },
    searchRow: { flexDirection: 'row', gap: 8 }, input: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.ink, flex: 1, minHeight: 44, paddingHorizontal: 12 },
    quantRow: { alignItems: 'center', flexDirection: 'row', gap: 8 }, quantInput: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minWidth: 110, paddingHorizontal: 10, paddingVertical: 7 },
    primaryButton: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 11, justifyContent: 'center', minHeight: 40, paddingHorizontal: 13 }, primaryText: { color: '#fff', fontSize: 12, fontWeight: '800' },
    secondaryButton: { alignItems: 'center', borderColor: colors.border, borderRadius: 11, borderWidth: 1, justifyContent: 'center', minHeight: 40, paddingHorizontal: 13 }, secondaryText: { color: colors.ink, fontSize: 12, fontWeight: '700' },
    disabled: { opacity: 0.45 },
    modelCardDisabled: { opacity: 0.55 },
    loadingButtonContent: { alignItems: 'center', flexDirection: 'row', gap: 7 },
    card: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 7, padding: 13 }, cardSelected: { borderColor: colors.primary, borderWidth: 2 }, cardTitle: { color: colors.ink, flex: 1, fontSize: 13, fontWeight: '800' },
    modelTitleRow: { alignItems: 'center', flexDirection: 'row', gap: 8 }, badge: { backgroundColor: colors.primarySoft, borderRadius: 10, color: colors.primary, fontSize: 10, fontWeight: '800', overflow: 'hidden', paddingHorizontal: 8, paddingVertical: 4 }, actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
    processingBadge: { backgroundColor: colors.dangerSoft, borderRadius: 10, color: colors.danger, fontSize: 10, fontWeight: '800', overflow: 'hidden', paddingHorizontal: 8, paddingVertical: 4 },
    job: { backgroundColor: colors.background, borderRadius: 14, gap: 7, padding: 13 }, jobHeader: { alignItems: 'center', flexDirection: 'row', gap: 8 }, dismissButton: { alignItems: 'center', borderRadius: 10, height: 30, justifyContent: 'center', width: 30 }, dismissButtonPressed: { backgroundColor: colors.dangerSoft }, dismissText: { color: colors.muted, fontSize: 22, lineHeight: 24 }, track: { backgroundColor: colors.border, borderRadius: 4, height: 7, overflow: 'hidden' }, fill: { backgroundColor: colors.primary, borderRadius: 4, height: 7 },
    message: { backgroundColor: colors.primarySoft, borderRadius: 10, color: colors.ink, fontSize: 12, lineHeight: 18, padding: 10 }, error: { color: '#ef6b73', fontSize: 12, lineHeight: 18 },
    headerIconButton: { alignItems: 'center', borderRadius: 12, height: 42, justifyContent: 'center', width: 42 },
    headerIcon: { height: 24, resizeMode: 'contain', width: 24 },
    expandTogglePressed: { backgroundColor: colors.primarySoft },
    emptyDownload: { backgroundColor: colors.subtle, borderRadius: 12, color: colors.muted, fontSize: 12, lineHeight: 18, padding: 12, textAlign: 'center' },
  });
}
