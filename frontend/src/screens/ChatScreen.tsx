import { useAudioPlayer } from 'expo-audio';
import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from '../api';
import { colors } from '../theme';
import type { Message, Session } from '../types';

type Props = {
  token: string;
  activeSessionId?: string;
  onSessionChange: (id: string) => void;
};

function AudioButton({ uri }: { uri: string }) {
  const player = useAudioPlayer(uri);
  const play = async () => {
    await player.seekTo(0);
    player.play();
  };
  return (
    <Pressable onPress={() => void play()} style={styles.audioButton}>
      <Text style={styles.audioText}>▶ 음성으로 듣기</Text>
    </Pressable>
  );
}

export function ChatScreen({ token, activeSessionId, onSessionChange }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [error, setError] = useState('');
  const scrollRef = useRef<ScrollView>(null);

  const loadSessions = async () => {
    const items = await api.sessions(token);
    setSessions(items);
    if (!activeSessionId && items[0]) onSessionChange(items[0].id);
  };

  useEffect(() => { void loadSessions(); }, [token]);
  useEffect(() => {
    if (!activeSessionId) { setMessages([]); return; }
    void api.history(token, activeSessionId).then(setMessages).catch((reason) => setError(reason.message));
  }, [activeSessionId, token]);

  const send = async () => {
    const value = text.trim();
    if (!value || busy) return;
    setText('');
    setBusy(true);
    setError('');
    try {
      const response = await api.chat(token, value, activeSessionId, undefined, true);
      onSessionChange(response.session.id);
      setMessages((current) => [...current, response.message]);
      await loadSessions();
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '메시지를 보내지 못했어요.');
      setText(value);
    } finally {
      setBusy(false);
    }
  };

  const chooseSession = (id: string) => {
    onSessionChange(id);
    setDrawer(false);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.root} keyboardVerticalOffset={90}>
      <View style={styles.header}>
        <Pressable accessibilityLabel="대화 목록" onPress={() => setDrawer(true)} style={styles.headerButton}><Text style={styles.headerIcon}>☰</Text></Pressable>
        <View style={styles.headerTitleWrap}>
          <Text numberOfLines={1} style={styles.headerTitle}>{sessions.find((item) => item.id === activeSessionId)?.title ?? 'MemoryPal Chat'}</Text>
          <Text style={styles.headerSub}>기억을 이어서 대화해요</Text>
        </View>
        <Pressable
          accessibilityLabel="새 대화"
          onPress={() => { setMessages([]); onSessionChange(''); }}
          style={styles.headerButton}
        ><Text style={styles.plus}>＋</Text></Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.messages}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        ref={scrollRef}
      >
        {!messages.length && (
          <View style={styles.empty}>
            <Text style={styles.emptyMark}>M</Text>
            <Text style={styles.emptyTitle}>새 이야기를 시작해 볼까요?</Text>
            <Text style={styles.emptyText}>메인 화면에서 말하거나 아래에 메시지를 입력해 주세요.</Text>
          </View>
        )}
        {messages.map((message) => (
          <View key={message.id}>
            <View style={[styles.bubble, styles.userBubble]}><Text style={styles.userText}>{message.user_text}</Text></View>
            <View style={[styles.bubble, styles.assistantBubble]}>
              <Text style={styles.assistantText}>{message.assistant_text}</Text>
              {!!message.audio_url && (
                <AudioButton uri={message.audio_url} />
              )}
            </View>
          </View>
        ))}
        {busy && <View style={[styles.bubble, styles.assistantBubble]}><ActivityIndicator color={colors.primary} /></View>}
      </ScrollView>

      {!!error && <Text style={styles.error}>{error}</Text>}
      <View style={styles.composer}>
        <TextInput
          multiline
          onChangeText={setText}
          onSubmitEditing={() => void send()}
          placeholder="메시지를 입력하세요…"
          placeholderTextColor="#A49DAB"
          style={styles.input}
          value={text}
        />
        <Pressable disabled={!text.trim() || busy} onPress={() => void send()} style={[styles.send, (!text.trim() || busy) && styles.sendDisabled]}>
          <Text style={styles.sendText}>↑</Text>
        </Pressable>
      </View>

      <Modal animationType="slide" onRequestClose={() => setDrawer(false)} transparent visible={drawer}>
        <Pressable onPress={() => setDrawer(false)} style={styles.backdrop}>
          <Pressable onPress={() => undefined} style={styles.drawer}>
            <View style={styles.drawerHandle} />
            <Text style={styles.drawerTitle}>지난 대화</Text>
            <ScrollView>
              {sessions.map((session) => (
                <Pressable key={session.id} onPress={() => chooseSession(session.id)} style={[styles.sessionRow, session.id === activeSessionId && styles.sessionActive]}>
                  <Text numberOfLines={1} style={styles.sessionTitle}>{session.title}</Text>
                  <Text style={styles.sessionDate}>{new Date(session.updated_at).toLocaleDateString('ko-KR')}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  header: { minHeight: 68, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  headerButton: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  headerIcon: { color: colors.ink, fontSize: 21 },
  plus: { color: colors.primaryDark, fontSize: 26 },
  headerTitleWrap: { flex: 1, alignItems: 'center' },
  headerTitle: { color: colors.ink, fontSize: 15, fontWeight: '800', maxWidth: 230 },
  headerSub: { color: colors.muted, fontSize: 10, marginTop: 2 },
  messages: { flexGrow: 1, padding: 18, paddingBottom: 25 },
  empty: { alignItems: 'center', marginTop: 80, paddingHorizontal: 30 },
  emptyMark: { width: 52, height: 52, textAlign: 'center', textAlignVertical: 'center', paddingTop: 10, borderRadius: 18, overflow: 'hidden', backgroundColor: colors.primarySoft, color: colors.primaryDark, fontSize: 22, fontWeight: '900' },
  emptyTitle: { color: colors.ink, fontSize: 18, fontWeight: '800', marginTop: 18 },
  emptyText: { color: colors.muted, fontSize: 13, textAlign: 'center', lineHeight: 20, marginTop: 7 },
  bubble: { maxWidth: '84%', borderRadius: 20, padding: 14, marginBottom: 12 },
  userBubble: { alignSelf: 'flex-end', backgroundColor: colors.primary, borderBottomRightRadius: 6 },
  assistantBubble: { alignSelf: 'flex-start', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 6 },
  userText: { color: '#FFFFFF', fontSize: 15, lineHeight: 22 },
  assistantText: { color: colors.ink, fontSize: 15, lineHeight: 23 },
  audioButton: { alignSelf: 'flex-start', marginTop: 11, backgroundColor: colors.primarySoft, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 999 },
  audioText: { color: colors.primaryDark, fontSize: 11, fontWeight: '800' },
  error: { color: colors.danger, fontSize: 12, paddingHorizontal: 18, paddingVertical: 5 },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 9, padding: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
  input: { flex: 1, minHeight: 48, maxHeight: 110, backgroundColor: '#F6F3F8', borderRadius: 18, paddingHorizontal: 16, paddingTop: 13, paddingBottom: 12, color: colors.ink, fontSize: 15 },
  send: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  sendDisabled: { opacity: 0.35 },
  sendText: { color: '#FFFFFF', fontSize: 23, fontWeight: '800' },
  backdrop: { flex: 1, backgroundColor: 'rgba(31,24,40,0.36)', justifyContent: 'flex-end' },
  drawer: { maxHeight: '72%', minHeight: 320, backgroundColor: colors.surface, borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 20 },
  drawerHandle: { width: 42, height: 4, borderRadius: 99, backgroundColor: '#D7D0DC', alignSelf: 'center', marginBottom: 20 },
  drawerTitle: { color: colors.ink, fontSize: 22, fontWeight: '900', marginBottom: 15 },
  sessionRow: { padding: 15, borderRadius: 15, marginBottom: 5 },
  sessionActive: { backgroundColor: colors.primarySoft },
  sessionTitle: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  sessionDate: { color: colors.muted, fontSize: 11, marginTop: 4 },
});
