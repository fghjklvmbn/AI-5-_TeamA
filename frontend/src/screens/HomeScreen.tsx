import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '../api';
import { RecordingOrb } from '../components/RecordingOrb';
import { useLiveRecorder } from '../hooks/useLiveRecorder';
import { colors } from '../theme';
import type { User, Voice } from '../types';

type Props = {
  token: string;
  user: User;
  sessionId?: string;
  onConversation: (sessionId: string) => void;
};

export function HomeScreen({ token, user, sessionId, onConversation }: Props) {
  const recorder = useLiveRecorder(token);
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceId, setVoiceId] = useState<string>();
  const [processing, setProcessing] = useState(false);
  const [status, setStatus] = useState('가운데 버튼을 누르고 편하게 말해 보세요.');

  useEffect(() => {
    void api.voices(token).then((items) => {
      setVoices(items);
      setVoiceId(items[0]?.id);
    }).catch(() => setVoices([]));
  }, [token]);

  const toggleRecording = async () => {
    try {
      if (!recorder.isRecording) {
        setStatus('음성을 듣고 있어요. 자연스럽게 말씀해 주세요.');
        await recorder.start();
        return;
      }
      setProcessing(true);
      setStatus('기억을 살펴보고 답변을 만들고 있어요…');
      const transcript = await recorder.stop();
      if (!transcript) {
        setStatus('잘 들리지 않았어요. 조금 더 가까이에서 다시 말해 주세요.');
        return;
      }
      const response = await api.chat(token, transcript, sessionId, voiceId, true);
      setStatus('답변이 준비됐어요.');
      onConversation(response.session.id);
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : '음성 대화를 시작하지 못했어요.');
    } finally {
      setProcessing(false);
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
            <Text style={styles.liveLabel}>{recorder.isRecording ? '실시간 인식 중' : '인식된 내용'}</Text>
          </View>
          <Text style={styles.transcript}>
            {recorder.liveText || '말씀하신 내용이 여기에 실시간으로 표시돼요…'}
          </Text>
        </View>
      )}

      <View style={styles.voiceSection}>
        <Text style={styles.sectionLabel}>응답 음성</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.voiceRow}>
            {(voices.length ? voices : [{ id: 'default', voice_name: '기본 음성' }]).map((voice) => {
              const selected = (voiceId ?? 'default') === voice.id;
              return (
                <Pressable
                  key={voice.id}
                  onPress={() => voice.id !== 'default' && setVoiceId(voice.id)}
                  style={[styles.voiceChip, selected && styles.voiceChipSelected]}
                >
                  <Text style={[styles.voiceText, selected && styles.voiceTextSelected]}>{voice.voice_name}</Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, padding: 24, paddingBottom: 34 },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  greeting: { color: colors.primaryDark, fontSize: 13, fontWeight: '700', marginBottom: 6 },
  headline: { color: colors.ink, fontSize: 27, lineHeight: 35, fontWeight: '900', letterSpacing: -0.8 },
  avatar: { width: 42, height: 42, borderRadius: 16, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.primaryDark, fontWeight: '800', fontSize: 17 },
  orbArea: { alignItems: 'center', marginTop: 34 },
  spinner: { position: 'absolute', top: 106 },
  status: { color: colors.muted, textAlign: 'center', fontSize: 13, marginTop: 4, minHeight: 38, maxWidth: 300, lineHeight: 19 },
  transcriptCard: { backgroundColor: colors.primarySoft, borderRadius: 22, padding: 18, marginTop: 15, borderWidth: 1, borderColor: '#E4DAFC' },
  liveRow: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 9 },
  liveDot: { width: 8, height: 8, borderRadius: 99, backgroundColor: colors.primary },
  liveLabel: { color: colors.primaryDark, fontSize: 12, fontWeight: '800' },
  transcript: { color: colors.ink, fontSize: 15, lineHeight: 23 },
  voiceSection: { marginTop: 24 },
  sectionLabel: { color: colors.ink, fontWeight: '800', fontSize: 14, marginBottom: 10 },
  voiceRow: { flexDirection: 'row', gap: 8 },
  voiceChip: { borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 15, paddingVertical: 10, borderRadius: 999 },
  voiceChipSelected: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  voiceText: { color: colors.muted, fontSize: 13, fontWeight: '600' },
  voiceTextSelected: { color: colors.primaryDark, fontWeight: '800' },
});
