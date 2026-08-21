import React from 'react';
import { Asset } from 'expo-asset';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';
import { CHARACTER_IDS } from '../character/ids';
import { CHARACTER_MANIFEST } from '../character/manifest';
import type { CharacterActivity, CharacterCue, CharacterId } from '../types';
import Live2DCanvas from './character/Live2DCanvas';

const ACTIVITY_TEXT: Record<CharacterActivity, string> = {
  idle: '대화를 기다리고 있어요',
  listening: '목소리를 듣고 있어요',
  thinking: '답변을 생각하고 있어요',
  speaking: '답변하고 있어요',
};

export default function CharacterStage({ characterId, activity, cue, onCharacterChange }: {
  characterId: CharacterId;
  activity: CharacterActivity;
  cue?: CharacterCue | null;
  onCharacterChange: (characterId: CharacterId) => void;
}) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const character = CHARACTER_MANIFEST[characterId];
  const sprites = character.assets;
  const spriteUri = Asset.fromModule(sprites.idle).uri;
  const talkingSpriteUri = Asset.fromModule(sprites.talking).uri;
  return <View style={styles.root}>
    <View style={styles.selector}>
      {CHARACTER_IDS.map((id) => <Pressable
        accessibilityLabel={`${CHARACTER_MANIFEST[id].name} 캐릭터 선택`}
        accessibilityState={{ selected: characterId === id }}
        key={id}
        onPress={() => onCharacterChange(id)}
        style={[styles.characterChoice, characterId === id && styles.characterChoiceActive]}
      ><Text style={[styles.characterChoiceText, characterId === id && styles.characterChoiceTextActive]}>{CHARACTER_MANIFEST[id].name}</Text></Pressable>)}
    </View>
    <View style={[styles.portrait, { borderColor: character.color }]}>
      <Live2DCanvas key={characterId} characterId={characterId} activity={activity} cue={cue} spriteUri={spriteUri} talkingSpriteUri={talkingSpriteUri} />
      <View style={[styles.activityDot, activity !== 'idle' && styles.activityDotActive]} />
    </View>
    <Text style={styles.name}>{character.name}</Text>
    <Text style={styles.activity}>{ACTIVITY_TEXT[activity]}</Text>
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  root: { flex: 1, minHeight: 280, alignItems: 'center', justifyContent: 'center', padding: 18, backgroundColor: colors.subtle },
  selector: { zIndex: 2, flexDirection: 'row', gap: 7, marginBottom: 12, padding: 4, borderRadius: 999, backgroundColor: colors.surface },
  characterChoice: { minWidth: 54, paddingHorizontal: 12, paddingVertical: 7, alignItems: 'center', borderRadius: 999 },
  characterChoiceActive: { backgroundColor: colors.primarySoft },
  characterChoiceText: { color: colors.muted, fontSize: 10, fontWeight: '800' },
  characterChoiceTextActive: { color: colors.primaryDark },
  portrait: { width: '100%', maxWidth: 390, height: 410, alignItems: 'center', justifyContent: 'center', overflow: 'hidden', borderRadius: 34, borderWidth: 2, backgroundColor: colors.surface },
  activityDot: { position: 'absolute', right: 14, bottom: 25, width: 14, height: 14, borderRadius: 7, borderWidth: 3, borderColor: colors.surface, backgroundColor: colors.muted },
  activityDotActive: { backgroundColor: colors.success },
  name: { marginTop: 12, color: colors.ink, fontSize: 18, fontWeight: '900' },
  activity: { marginTop: 4, color: colors.muted, fontSize: 11 },
});
