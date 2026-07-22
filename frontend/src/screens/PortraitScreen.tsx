import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../api';
import { useTheme, type ThemeColors } from '../theme';
import type { Persona, PortraitResponse, PortraitStatus } from '../types';

type Props = {
  token: string;
  persona: Persona;
};

const POLL_INTERVAL_MS = 4000;

function isAnalyzing(status?: PortraitStatus) {
  return status === 'queued' || status === 'analyzing';
}

function clampPercent(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

function formatCount(value?: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString('ko-KR') : '0';
}

function progressCopy(portrait: PortraitResponse) {
  if (portrait.status === 'queued') return '분석 순서를 기다리고 있어요.';
  const progress = clampPercent(portrait.progress_percent);
  if (progress < 30) return '대화에서 일상과 감정의 단서를 찾고 있어요.';
  if (progress < 65) return '세션별 특징을 요약하고 중요도를 살피고 있어요.';
  if (progress < 90) return '대화의 특징을 페르소나와 연결하고 있어요.';
  return '자화상 문장과 정확도를 다듬고 있어요.';
}

export function PortraitScreen({ token, persona }: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const [portrait, setPortrait] = useState<PortraitResponse>();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const requestInFlight = useRef(false);

  const loadPortrait = useCallback(async (showLoading = false) => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    if (showLoading) setLoading(true);
    try {
      const next = await api.portrait(token);
      setPortrait(next);
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '자화상을 불러오지 못했어요.');
    } finally {
      requestInFlight.current = false;
      if (showLoading) setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadPortrait(true);
  }, [loadPortrait]);

  useEffect(() => {
    if (!isAnalyzing(portrait?.status)) return undefined;
    const timer = setInterval(() => {
      void loadPortrait();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [loadPortrait, portrait?.status]);

  const generate = async () => {
    if (generating) return;
    setGenerating(true);
    setError('');
    try {
      const next = await api.generatePortrait(token, persona);
      setPortrait(next);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '자화상 분석을 시작하지 못했어요.');
    } finally {
      setGenerating(false);
    }
  };

  if (loading && !portrait) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color={colors.primary} size="large" />
        <Text style={styles.loadingText}>자화상을 불러오고 있어요</Text>
      </View>
    );
  }

  if (!portrait && error) {
    return (
      <View style={styles.centered}>
        <View style={styles.errorSymbol}><Text style={styles.errorSymbolText}>!</Text></View>
        <Text style={styles.stateTitle}>자화상을 불러오지 못했어요</Text>
        <Text style={styles.stateDescription}>{error}</Text>
        <Pressable accessibilityRole="button" onPress={() => void loadPortrait(true)} style={styles.secondaryButton}>
          <Text style={styles.secondaryButtonText}>다시 불러오기</Text>
        </Pressable>
      </View>
    );
  }

  const current = portrait ?? { status: 'empty' as const };
  const progress = clampPercent(current.progress_percent);
  const accuracy = clampPercent(current.accuracy_percent);

  return (
    <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>AI SELF PORTRAIT</Text>
        <Text style={styles.title}>자화상</Text>
        <Text style={styles.subtitle}>지금까지 나눈 대화 속에서 당신다운 모습을 발견해요.</Text>
      </View>

      {current.status === 'empty' && (
        <View style={styles.stateCard}>
          <View style={styles.portraitMark}>
            <View style={styles.portraitMarkInner}><Text style={styles.portraitMarkText}>◐</Text></View>
          </View>
          <Text style={styles.stateTitle}>대화로 그리는 나의 모습</Text>
          <Text style={styles.stateDescription}>
            일상과 감정이 담긴 대화에 더 큰 비중을 두고, 단순 지식 질문은 제외해 당신의 특징을 종합해요.
          </Text>
          <View style={styles.timeNotice}>
            <Text style={styles.timeIcon}>◷</Text>
            <View style={styles.timeCopy}>
              <Text style={styles.timeTitle}>예상 분석 시간 5~20분</Text>
              <Text style={styles.timeDescription}>분석 중에는 다른 메뉴를 이용해도 괜찮아요.</Text>
            </View>
          </View>
          <Pressable
            accessibilityRole="button"
            disabled={generating}
            onPress={() => void generate()}
            style={[styles.primaryButton, generating && styles.disabledButton]}
          >
            {generating ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryButtonText}>나의 자화상 만들기</Text>}
          </Pressable>
        </View>
      )}

      {isAnalyzing(current.status) && (
        <View style={styles.stateCard}>
          <View style={styles.analyzingBadge}>
            <ActivityIndicator color={colors.primary} size="small" />
            <Text style={styles.analyzingBadgeText}>{current.status === 'queued' ? '분석 준비 중' : '대화 분석 중'}</Text>
          </View>
          <Text style={styles.stateTitle}>당신의 모습을 천천히 그리고 있어요</Text>
          <Text style={styles.stateDescription}>{progressCopy(current)}</Text>
          <View style={styles.progressHeader}>
            <Text style={styles.progressLabel}>전체 진행률</Text>
            <Text style={styles.progressValue}>{Math.round(progress)}%</Text>
          </View>
          <View
            accessibilityLabel={`자화상 분석 ${Math.round(progress)}% 완료`}
            accessibilityRole="progressbar"
            accessibilityValue={{ min: 0, max: 100, now: Math.round(progress) }}
            style={styles.progressTrack}
          >
            <View style={[styles.progressFill, { width: `${progress}%` }]} />
          </View>
          <View style={styles.statRow}>
            <View style={styles.statItem}>
              <Text style={styles.statValue}>{formatCount(current.analyzed_sessions)}</Text>
              <Text style={styles.statLabel}>분석한 세션</Text>
            </View>
            <View style={styles.statDivider} />
            <View style={styles.statItem}>
              <Text style={styles.statValue}>{formatCount(current.analyzed_messages)}</Text>
              <Text style={styles.statLabel}>살펴본 대화</Text>
            </View>
          </View>
          <Text style={styles.backgroundHint}>이 화면을 나가도 분석은 계속 진행돼요.</Text>
        </View>
      )}

      {current.status === 'complete' && (
        <>
          <View style={styles.resultCard}>
            <View style={styles.resultMark}><Text style={styles.resultMarkText}>◐</Text></View>
            <Text style={styles.resultEyebrow}>당신을 닮은 두 글자</Text>
            <Text style={styles.resultHeadline}>당신의 자화상은 <Text style={styles.resultTitle}>{current.title?.trim() || '미정'}</Text>입니다.</Text>
            <View style={styles.summaryDivider} />
            <Text selectable style={styles.summary}>{current.summary?.trim() || '아직 자화상 설명이 준비되지 않았어요.'}</Text>
          </View>

          <View style={styles.accuracyCard}>
            <View style={styles.accuracyHeader}>
              <View>
                <Text style={styles.metricEyebrow}>VECTOR SIMILARITY</Text>
                <Text style={styles.accuracyTitle}>자화상 정확도</Text>
              </View>
              <Text style={styles.accuracyValue}>{Math.round(accuracy)}%</Text>
            </View>
            <View style={styles.accuracyTrack}>
              <View style={[styles.accuracyFill, { width: `${accuracy}%` }]} />
            </View>
            <Text style={styles.accuracyDescription}>대화에서 찾은 특징들과 완성된 자화상의 벡터 유사도를 바탕으로 계산했어요.</Text>
          </View>

          <View style={styles.countCard}>
            <View style={styles.countItem}>
              <Text style={styles.countValue}>{formatCount(current.analyzed_sessions)}</Text>
              <Text style={styles.countLabel}>분석 세션</Text>
            </View>
            <View style={styles.countDivider} />
            <View style={styles.countItem}>
              <Text style={styles.countValue}>{formatCount(current.analyzed_messages)}</Text>
              <Text style={styles.countLabel}>분석 대화</Text>
            </View>
          </View>

          <Pressable
            accessibilityRole="button"
            disabled={generating}
            onPress={() => void generate()}
            style={[styles.secondaryButton, styles.regenerateButton, generating && styles.disabledButton]}
          >
            {generating ? <ActivityIndicator color={colors.primaryDark} /> : <Text style={styles.secondaryButtonText}>다시 분석하기</Text>}
          </Pressable>
        </>
      )}

      {current.status === 'failed' && (
        <View style={styles.stateCard}>
          <View style={styles.errorSymbol}><Text style={styles.errorSymbolText}>!</Text></View>
          <Text style={styles.stateTitle}>분석을 완료하지 못했어요</Text>
          <Text style={styles.stateDescription}>{current.error || '잠시 후 다시 분석을 시작해 주세요.'}</Text>
          <Pressable
            accessibilityRole="button"
            disabled={generating}
            onPress={() => void generate()}
            style={[styles.primaryButton, generating && styles.disabledButton]}
          >
            {generating ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryButtonText}>다시 분석하기</Text>}
          </Pressable>
        </View>
      )}

      {!!error && !!portrait && <Text style={styles.inlineError}>{error}</Text>}
    </ScrollView>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  content: { flexGrow: 1, paddingHorizontal: 22, paddingTop: 23, paddingBottom: 34 },
  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28, backgroundColor: colors.background },
  loadingText: { color: colors.muted, fontSize: 13, marginTop: 14 },
  header: { marginBottom: 20 },
  eyebrow: { color: colors.primaryDark, fontSize: 10, fontWeight: '900', letterSpacing: 1.6 },
  title: { color: colors.ink, fontSize: 29, fontWeight: '900', letterSpacing: -0.8, marginTop: 4 },
  subtitle: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: 7 },
  stateCard: { alignItems: 'center', borderRadius: 25, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 20, paddingVertical: 25 },
  portraitMark: { width: 92, height: 92, borderRadius: 46, borderWidth: 1, borderColor: colors.lilac, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', marginBottom: 19 },
  portraitMarkInner: { width: 64, height: 64, borderRadius: 32, borderWidth: 1, borderColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  portraitMarkText: { color: colors.primaryDark, fontSize: 35, lineHeight: 39 },
  stateTitle: { color: colors.ink, fontSize: 19, lineHeight: 26, fontWeight: '900', textAlign: 'center' },
  stateDescription: { color: colors.muted, fontSize: 13, lineHeight: 21, textAlign: 'center', marginTop: 9 },
  timeNotice: { width: '100%', flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 16, backgroundColor: colors.primarySoft, padding: 14, marginTop: 21 },
  timeIcon: { color: colors.primaryDark, fontSize: 24 },
  timeCopy: { flex: 1 },
  timeTitle: { color: colors.primaryDark, fontSize: 12, fontWeight: '900' },
  timeDescription: { color: colors.muted, fontSize: 10, lineHeight: 15, marginTop: 3 },
  primaryButton: { width: '100%', minHeight: 52, borderRadius: 16, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 18, paddingHorizontal: 18 },
  primaryButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '900' },
  secondaryButton: { minWidth: 160, minHeight: 48, borderRadius: 15, borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 20, marginTop: 20 },
  secondaryButtonText: { color: colors.primaryDark, fontSize: 13, fontWeight: '900' },
  disabledButton: { opacity: 0.55 },
  analyzingBadge: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 999, backgroundColor: colors.primarySoft, paddingHorizontal: 13, paddingVertical: 8, marginBottom: 18 },
  analyzingBadgeText: { color: colors.primaryDark, fontSize: 11, fontWeight: '900' },
  progressHeader: { width: '100%', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 25 },
  progressLabel: { color: colors.ink, fontSize: 12, fontWeight: '800' },
  progressValue: { color: colors.primaryDark, fontSize: 17, fontWeight: '900' },
  progressTrack: { width: '100%', height: 10, borderRadius: 99, backgroundColor: colors.subtle, overflow: 'hidden', marginTop: 9 },
  progressFill: { height: '100%', borderRadius: 99, backgroundColor: colors.primary },
  statRow: { width: '100%', flexDirection: 'row', alignItems: 'center', borderRadius: 17, backgroundColor: colors.subtle, marginTop: 20, paddingVertical: 14 },
  statItem: { flex: 1, alignItems: 'center' },
  statValue: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  statLabel: { color: colors.muted, fontSize: 10, marginTop: 3 },
  statDivider: { width: 1, height: 30, backgroundColor: colors.border },
  backgroundHint: { color: colors.muted, fontSize: 10, marginTop: 15 },
  resultCard: { alignItems: 'center', borderRadius: 27, borderWidth: 1, borderColor: colors.lilac, backgroundColor: colors.surface, paddingHorizontal: 21, paddingVertical: 25 },
  resultMark: { width: 50, height: 50, borderRadius: 18, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  resultMarkText: { color: colors.primaryDark, fontSize: 26 },
  resultEyebrow: { color: colors.primaryDark, fontSize: 10, fontWeight: '900', letterSpacing: 1, marginTop: 15 },
  resultHeadline: { color: colors.ink, fontSize: 21, lineHeight: 31, fontWeight: '800', textAlign: 'center', marginTop: 6 },
  resultTitle: { color: colors.primaryDark, fontSize: 28, fontWeight: '900' },
  summaryDivider: { width: 36, height: 2, borderRadius: 99, backgroundColor: colors.lilac, marginVertical: 19 },
  summary: { color: colors.ink, fontSize: 14, lineHeight: 24, textAlign: 'left', width: '100%' },
  accuracyCard: { borderRadius: 21, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18, marginTop: 13 },
  accuracyHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  metricEyebrow: { color: colors.muted, fontSize: 8, fontWeight: '800', letterSpacing: 1.2 },
  accuracyTitle: { color: colors.ink, fontSize: 14, fontWeight: '900', marginTop: 3 },
  accuracyValue: { color: colors.primaryDark, fontSize: 29, fontWeight: '900' },
  accuracyTrack: { height: 7, borderRadius: 99, backgroundColor: colors.subtle, overflow: 'hidden', marginTop: 14 },
  accuracyFill: { height: '100%', borderRadius: 99, backgroundColor: colors.primary },
  accuracyDescription: { color: colors.muted, fontSize: 10, lineHeight: 16, marginTop: 11 },
  countCard: { flexDirection: 'row', alignItems: 'center', borderRadius: 21, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginTop: 13, paddingVertical: 16 },
  countItem: { flex: 1, alignItems: 'center' },
  countValue: { color: colors.ink, fontSize: 20, fontWeight: '900' },
  countLabel: { color: colors.muted, fontSize: 10, marginTop: 3 },
  countDivider: { width: 1, height: 34, backgroundColor: colors.border },
  regenerateButton: { width: '100%', marginTop: 14 },
  errorSymbol: { width: 52, height: 52, borderRadius: 19, backgroundColor: colors.dangerSoft, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  errorSymbolText: { color: colors.danger, fontSize: 24, fontWeight: '900' },
  inlineError: { color: colors.danger, fontSize: 11, lineHeight: 17, textAlign: 'center', marginTop: 12 },
});
