import { useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import React, { useCallback, useEffect, useRef } from 'react';
import { Platform, Pressable, StyleSheet, Text } from 'react-native';

import { playWebAudio, publishCharacterAudioState } from '../audioPlayback';
import { useTheme } from '../theme';

type Props = {
  uri: string;
  messageId: string;
  onError: (message: string) => void;
  autoPlay?: boolean;
  controls?: boolean;
};

export function MessageAudioButton({
  uri,
  messageId,
  onError,
  autoPlay = false,
  controls = true,
}: Props) {
  const { colors } = useTheme();
  const player = useAudioPlayer(uri);
  const playerStatus = useAudioPlayerStatus(player);
  const autoPlayedUriRef = useRef<string | undefined>(undefined);
  const play = useCallback(async () => {
    try {
      if (Platform.OS === 'web') {
        await playWebAudio(uri, messageId);
        return;
      }
      await player.seekTo(0);
      player.play();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : '음성을 재생하지 못했어요.');
    }
  }, [messageId, onError, player, uri]);

  useEffect(() => {
    if (Platform.OS === 'web') return;
    publishCharacterAudioState(playerStatus.playing ? 0.45 : 0, playerStatus.playing, messageId);
  }, [messageId, playerStatus.playing]);

  useEffect(() => {
    if (!autoPlay || autoPlayedUriRef.current === uri) return;
    autoPlayedUriRef.current = uri;
    void play();
  }, [autoPlay, play, uri]);

  if (!controls) return null;

  return (
    <Pressable
      onPress={() => void play()}
      style={[styles.button, { backgroundColor: colors.primarySoft }]}
    >
      <Text style={[styles.text, { color: colors.primary }]}>▶ 음성으로 듣기</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { alignSelf: 'flex-start', borderRadius: 16, marginTop: 10, paddingHorizontal: 12, paddingVertical: 7 },
  text: { fontSize: 12, fontWeight: '800' },
});
