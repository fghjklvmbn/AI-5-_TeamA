import React from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';

export default function Live2DCanvas({ characterId, activity, cue }: {
  characterId: CharacterId; activity: CharacterActivity; cue?: CharacterCue | null; spriteUri?: string;
}) {
  const source = characterId === 'haru'
    ? require('../../../assets/memory-mascot.png')
    : require('../../../assets/nari-assistant.png');
  return <View style={styles.root}><Image resizeMode="contain" source={source} style={styles.mascot} /><Text style={styles.caption}>{activity === 'speaking' ? '음성 립싱크 중' : cue?.emotion ?? 'neutral'}</Text></View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  mascot: { width: '92%', height: '92%' },
  face: { width: 170, height: 230, borderRadius: 85, alignItems: 'center', justifyContent: 'center', backgroundColor: '#8F6AE8' },
  nari: { backgroundColor: '#D16E9E' },
  eye: { color: '#FFFFFF', fontSize: 30, fontWeight: '900' },
  mouth: { color: '#FFFFFF', fontSize: 26, marginTop: 22 },
  caption: { marginTop: 12, color: '#8D8493', fontSize: 10 },
});
