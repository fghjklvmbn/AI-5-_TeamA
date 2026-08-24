import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from '../api';
import { useTheme, type ThemeColors } from '../theme';
import type { MemoryItem } from '../types';

const labels: Record<MemoryItem['memory_type'], { label: string; icon: string }> = {
  preference: { label: '취향', icon: '♥' },
  profile: { label: '프로필', icon: '●' },
  fact: { label: '사실', icon: '◆' },
  schedule: { label: '일정', icon: '▣' },
  relationship: { label: '관계', icon: '∞' },
};

export function MemoryScreen({ token }: { token: string }) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [content, setContent] = useState('');
  const [type, setType] = useState<MemoryItem['memory_type']>('fact');
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selectedType, setSelectedType] = useState<'all' | MemoryItem['memory_type']>('all');
  const [searching, setSearching] = useState(false);

  const load = async (signal?: AbortSignal) => {
    const memoryType = selectedType === 'all' ? undefined : selectedType;
    return api.memories(token, { query, memoryType, signal });
  };

  useEffect(() => {
    const controller = new AbortController();
    const delay = query.trim() ? 250 : 0;
    const timer = setTimeout(() => {
      setSearching(true);
      void load(controller.signal).then((next) => {
        if (controller.signal.aborted) return;
        setItems(next);
        setError('');
      }).catch((reason) => {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : '기억을 불러오지 못했어요.');
        }
      }).finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
          setSearching(false);
        }
      });
    }, delay);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [token, query, selectedType]);

  const remove = async (id: string) => {
    setItems((current) => current.filter((item) => item.id !== id));
    try { await api.deleteMemory(token, id); }
    catch {
      try { setItems(await load()); } catch { /* Keep the optimistic view if refresh also fails. */ }
    }
  };

  const add = async () => {
    if (!content.trim()) return;
    try {
      const item = await api.addMemory(token, type, content.trim());
      const matchesType = selectedType === 'all' || item.memory_type === selectedType;
      const matchesQuery = !query.trim() || item.content.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
      if (matchesType && matchesQuery) {
        setItems((current) => [item, ...current.filter((value) => value.id !== item.id)]);
      }
      setContent('');
      setAdding(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '기억을 저장하지 못했어요.');
    }
  };

  return (
    <View style={styles.root}>
      <View style={styles.header}>
        <View>
          <Text style={styles.eyebrow}>LONG-TERM MEMORY</Text>
          <Text style={styles.title}>MemoryPal의 기억</Text>
          <Text style={styles.subtitle}>대화에 도움이 되는 내용만 사용자별로 보관해요.</Text>
        </View>
        <Pressable accessibilityLabel="기억 직접 추가" onPress={() => setAdding(true)} style={styles.addButton}><Text style={styles.addIcon}>＋</Text></Pressable>
      </View>
      <View style={styles.searchSection}>
        <View style={styles.searchBox}>
          <Text style={styles.searchIcon}>⌕</Text>
          <TextInput
            accessibilityLabel="기억 검색"
            onChangeText={setQuery}
            placeholder={selectedType === 'all' ? '기억 내용 검색' : `${labels[selectedType].label} 기억 검색`}
            placeholderTextColor={colors.muted}
            returnKeyType="search"
            style={styles.searchInput}
            value={query}
          />
          {searching && <ActivityIndicator color={colors.primary} size="small" />}
          {!!query && !searching && (
            <Pressable accessibilityLabel="검색어 지우기" hitSlop={8} onPress={() => setQuery('')}>
              <Text style={styles.searchClear}>×</Text>
            </Pressable>
          )}
        </View>
        <ScrollView
          contentContainerStyle={styles.filterRow}
          horizontal
          showsHorizontalScrollIndicator={false}
        >
          {(['all', ...Object.keys(labels)] as ('all' | MemoryItem['memory_type'])[]).map((key) => {
            const active = selectedType === key;
            const label = key === 'all' ? '전체' : labels[key].label;
            return (
              <Pressable
                accessibilityLabel={`${label} 기억만 보기`}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                key={key}
                onPress={() => setSelectedType(key)}
                style={[styles.filterChip, active && styles.filterChipActive]}
              >
                {key !== 'all' && <Text style={[styles.filterIcon, active && styles.filterTextActive]}>{labels[key].icon}</Text>}
                <Text style={[styles.filterText, active && styles.filterTextActive]}>{label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
        {!loading && (
          <Text accessibilityLiveRegion="polite" style={styles.resultCount}>
            {selectedType === 'all' ? '전체' : labels[selectedType].label} 기억 {items.length}개
          </Text>
        )}
      </View>
      {loading ? <ActivityIndicator color={colors.primary} style={{ marginTop: 80 }} /> : (
        <ScrollView contentContainerStyle={styles.list} showsVerticalScrollIndicator={false}>
          {!items.length && (
            <View style={styles.empty}>
              <Text style={styles.emptyIcon}>◇</Text>
              <Text style={styles.emptyTitle}>{query.trim() || selectedType !== 'all' ? '조건에 맞는 기억이 없어요' : '아직 저장된 기억이 없어요'}</Text>
              <Text style={styles.emptyText}>
                {query.trim() || selectedType !== 'all'
                  ? '검색어나 분류를 바꾸어 다시 찾아보세요.'
                  : `“나는 따뜻한 라테를 좋아해”처럼 말하면\nMemoryPal이 다음 대화에 기억해 둘게요.`}
              </Text>
              {(query.trim() || selectedType !== 'all') && (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => { setQuery(''); setSelectedType('all'); }}
                  style={styles.resetButton}
                >
                  <Text style={styles.resetButtonText}>검색 조건 초기화</Text>
                </Pressable>
              )}
            </View>
          )}
          {items.map((item) => (
            <View key={item.id} style={styles.card}>
              <View style={styles.cardTop}>
                <View style={styles.typePill}>
                  <Text style={styles.typeIcon}>{labels[item.memory_type].icon}</Text>
                  <Text style={styles.typeText}>{labels[item.memory_type].label}</Text>
                </View>
                <Pressable accessibilityLabel="기억 삭제" onPress={() => void remove(item.id)} hitSlop={10}><Text style={styles.delete}>×</Text></Pressable>
              </View>
              <Text style={styles.content}>{item.content}</Text>
              <Text style={styles.date}>{new Date(item.updated_at).toLocaleDateString('ko-KR')}에 기억함</Text>
            </View>
          ))}
          {!!error && <Text style={styles.error}>{error}</Text>}
        </ScrollView>
      )}

      <Modal animationType="fade" onRequestClose={() => setAdding(false)} transparent visible={adding}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>기억 직접 추가</Text>
            <Text style={styles.modalSubtitle}>MemoryPal이 다음 대화에서 참고할 내용을 적어 주세요.</Text>
            <View style={styles.typeRow}>
              {(Object.keys(labels) as MemoryItem['memory_type'][]).map((key) => (
                <Pressable key={key} onPress={() => setType(key)} style={[styles.typeChoice, type === key && styles.typeChoiceActive]}>
                  <Text style={[styles.typeChoiceText, type === key && styles.typeChoiceTextActive]}>{labels[key].label}</Text>
                </Pressable>
              ))}
            </View>
            <TextInput
              multiline
              onChangeText={setContent}
              placeholder="예: 나는 산책할 때 재즈 듣는 걸 좋아해"
              placeholderTextColor="#A49DAB"
              style={styles.input}
              value={content}
            />
            <View style={styles.actions}>
              <Pressable onPress={() => setAdding(false)} style={styles.cancel}><Text style={styles.cancelText}>취소</Text></Pressable>
              <Pressable disabled={!content.trim()} onPress={() => void add()} style={[styles.save, !content.trim() && { opacity: 0.4 }]}><Text style={styles.saveText}>기억하기</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  root: { flex: 1 },
  header: { padding: 24, paddingBottom: 17, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  eyebrow: { color: colors.primaryDark, fontSize: 10, letterSpacing: 1.5, fontWeight: '800' },
  title: { color: colors.ink, fontSize: 25, fontWeight: '900', letterSpacing: -0.6, marginTop: 5 },
  subtitle: { color: colors.muted, fontSize: 12, marginTop: 7, maxWidth: 285 },
  addButton: { width: 44, height: 44, borderRadius: 16, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  addIcon: { color: '#FFFFFF', fontSize: 25, lineHeight: 28 },
  searchSection: { paddingHorizontal: 20, paddingBottom: 12 },
  searchBox: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 9, borderWidth: 1, borderColor: colors.border, borderRadius: 16, backgroundColor: colors.input, paddingHorizontal: 13 },
  searchIcon: { color: colors.primaryDark, fontSize: 22, transform: [{ rotate: '-20deg' }] },
  searchInput: { flex: 1, color: colors.ink, fontSize: 13, paddingVertical: 12 },
  searchClear: { color: colors.muted, fontSize: 23, lineHeight: 25 },
  filterRow: { gap: 7, paddingTop: 11, paddingRight: 8 },
  filterChip: { minHeight: 36, flexDirection: 'row', alignItems: 'center', gap: 5, borderWidth: 1, borderColor: colors.border, borderRadius: 999, backgroundColor: colors.surface, paddingHorizontal: 12 },
  filterChipActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  filterIcon: { color: colors.muted, fontSize: 10 },
  filterText: { color: colors.muted, fontSize: 11, fontWeight: '800' },
  filterTextActive: { color: colors.primaryDark },
  resultCount: { color: colors.muted, fontSize: 10, marginTop: 10, paddingHorizontal: 2 },
  list: { paddingHorizontal: 20, paddingBottom: 30 },
  empty: { alignItems: 'center', marginTop: 78 },
  emptyIcon: { fontSize: 48, color: colors.primary },
  emptyTitle: { color: colors.ink, fontSize: 18, fontWeight: '800', marginTop: 14 },
  emptyText: { color: colors.muted, fontSize: 13, lineHeight: 21, textAlign: 'center', marginTop: 8 },
  resetButton: { minHeight: 42, alignItems: 'center', justifyContent: 'center', borderRadius: 14, backgroundColor: colors.primarySoft, paddingHorizontal: 18, marginTop: 18 },
  resetButtonText: { color: colors.primaryDark, fontSize: 12, fontWeight: '900' },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 21, padding: 17, marginBottom: 12 },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  typePill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.primarySoft, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 },
  typeIcon: { color: colors.primaryDark, fontSize: 11 },
  typeText: { color: colors.primaryDark, fontSize: 11, fontWeight: '800' },
  delete: { color: colors.muted, fontSize: 24, fontWeight: '300' },
  content: { color: colors.ink, fontSize: 15, lineHeight: 23, fontWeight: '600', marginTop: 13 },
  date: { color: colors.muted, fontSize: 10, marginTop: 10 },
  error: { color: colors.danger, textAlign: 'center', fontSize: 12, marginTop: 10 },
  modalBackdrop: { flex: 1, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center', padding: 22 },
  modalCard: { width: '100%', maxWidth: 460, borderRadius: 26, backgroundColor: colors.surface, padding: 22 },
  modalTitle: { color: colors.ink, fontSize: 21, fontWeight: '900' },
  modalSubtitle: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: 7 },
  typeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 18 },
  typeChoice: { paddingHorizontal: 11, paddingVertical: 8, borderRadius: 999, borderWidth: 1, borderColor: colors.border },
  typeChoiceActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  typeChoiceText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  typeChoiceTextActive: { color: colors.primaryDark },
  input: { minHeight: 115, marginTop: 15, borderRadius: 16, borderWidth: 1, borderColor: colors.border, padding: 14, color: colors.ink, fontSize: 14, textAlignVertical: 'top' },
  actions: { flexDirection: 'row', gap: 9, marginTop: 16 },
  cancel: { flex: 1, height: 48, borderRadius: 14, backgroundColor: colors.subtle, alignItems: 'center', justifyContent: 'center' },
  cancelText: { color: colors.muted, fontWeight: '800' },
  save: { flex: 1.4, height: 48, borderRadius: 14, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  saveText: { color: '#FFFFFF', fontWeight: '800' },
});

