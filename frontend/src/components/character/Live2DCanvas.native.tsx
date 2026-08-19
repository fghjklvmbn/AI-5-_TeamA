import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';

export default function Live2DCanvas({ characterId, activity, cue }: {
  characterId: CharacterId; activity: CharacterActivity; cue?: CharacterCue | null;
}) {
  return <View style={styles.root}><View style={[styles.face, characterId === 'nari' && styles.nari]}><Text style={styles.eye}>•  •</Text><Text style={styles.mouth}>{activity === 'speaking' ? '◯' : '—'}</Text></View><Text style={styles.caption}>{cue?.emotion ?? 'neutral'}</Text></View>;
}

const styles = StyleSheet.create({
  root: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  face: { width: 170, height: 230, borderRadius: 85, alignItems: 'center', justifyContent: 'center', backgroundColor: '#8F6AE8' },
  nari: { backgroundColor: '#D16E9E' },
  eye: { color: '#FFFFFF', fontSize: 30, fontWeight: '900' },
  mouth: { color: '#FFFFFF', fontSize: 26, marginTop: 22 },
  caption: { marginTop: 12, color: '#8D8493', fontSize: 10 },
});
