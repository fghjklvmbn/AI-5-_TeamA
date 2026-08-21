import React, { useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { subscribeCharacterAudio } from '../../audioPlayback';
import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';
import { CHARACTER_MANIFEST } from '../../character/manifest';

export default function Live2DCanvas({ characterId, activity, cue }: {
  characterId: CharacterId; activity: CharacterActivity; cue?: CharacterCue | null; spriteUri?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const [mouthOpen, setMouthOpen] = useState(false);
  const character = CHARACTER_MANIFEST[characterId];
  useEffect(() => subscribeCharacterAudio((_level, nextPlaying) => setPlaying(nextPlaying)), []);
  useEffect(() => {
    if (!playing) {
      setMouthOpen(false);
      return undefined;
    }
    const interval = setInterval(() => setMouthOpen((open) => !open), 110);
    return () => clearInterval(interval);
  }, [playing]);
  const speaking = playing || activity === 'speaking';
  const source = speaking && mouthOpen ? character.assets.talking : character.assets.idle;
  return <View style={styles.root}>
    <Image resizeMode="contain" source={source} style={[styles.mascot, speaking && styles.speaking]} />
    <Text style={styles.caption}>{speaking ? '음성 립싱크 중' : cue?.emotion ?? 'neutral'}</Text>
  </View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  mascot: { width: '92%', height: '92%' },
  speaking: { transform: [{ scale: 1.008 }] },
  face: { width: 170, height: 230, borderRadius: 85, alignItems: 'center', justifyContent: 'center', backgroundColor: '#8F6AE8' },
  nari: { backgroundColor: '#D16E9E' },
  eye: { color: '#FFFFFF', fontSize: 30, fontWeight: '900' },
  mouth: { color: '#FFFFFF', fontSize: 26, marginTop: 22 },
  caption: { marginTop: 12, color: '#8D8493', fontSize: 10 },
});
