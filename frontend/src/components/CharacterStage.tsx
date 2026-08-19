import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';
import type { CharacterActivity, CharacterId } from '../types';

const CHARACTERS: Record<CharacterId, { name: string; color: string; initial: string }> = {
  haru: { name: '하루', color: '#8F6AE8', initial: '하' },
  nari: { name: '나리', color: '#D16E9E', initial: '나' },
};

const ACTIVITY_TEXT: Record<CharacterActivity, string> = {
  idle: '대화를 기다리고 있어요',
  listening: '목소리를 듣고 있어요',
  thinking: '답변을 생각하고 있어요',
  speaking: '답변하고 있어요',
};

export default function CharacterStage({ characterId, activity, onCharacterChange }: {
  characterId: CharacterId;
  activity: CharacterActivity;
  onCharacterChange: (characterId: CharacterId) => void;
}) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const character = CHARACTERS[characterId];
  return <View style={styles.root}>
    <View style={styles.selector}>
      {(Object.keys(CHARACTERS) as CharacterId[]).map((id) => <Pressable
        accessibilityLabel={`${CHARACTERS[id].name} 캐릭터 선택`}
        accessibilityState={{ selected: characterId === id }}
        key={id}
        onPress={() => onCharacterChange(id)}
        style={[styles.characterChoice, characterId === id && styles.characterChoiceActive]}
      ><Text style={[styles.characterChoiceText, characterId === id && styles.characterChoiceTextActive]}>{CHARACTERS[id].name}</Text></Pressable>)}
    </View>
    <View style={[styles.portrait, { borderColor: character.color }]}>
      <View style={[styles.placeholderFace, { backgroundColor: character.color }]}><Text style={styles.initial}>{character.initial}</Text></View>
      <View style={[styles.activityDot, activity !== 'idle' && styles.activityDotActive]} />
    </View>
    <Text style={styles.name}>{character.name}</Text>
    <Text style={styles.activity}>{ACTIVITY_TEXT[activity]}</Text>
    <View style={styles.readyBadge}><Text style={styles.readyText}>Live2D 렌더러 연결 준비됨</Text></View>
  </View>;
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  root: { flex: 1, minHeight: 280, alignItems: 'center', justifyContent: 'center', padding: 18, backgroundColor: colors.subtle },
  selector: { position: 'absolute', top: 12, flexDirection: 'row', gap: 7, padding: 4, borderRadius: 999, backgroundColor: colors.surface },
  characterChoice: { minWidth: 54, paddingHorizontal: 12, paddingVertical: 7, alignItems: 'center', borderRadius: 999 },
  characterChoiceActive: { backgroundColor: colors.primarySoft },
  characterChoiceText: { color: colors.muted, fontSize: 10, fontWeight: '800' },
  characterChoiceTextActive: { color: colors.primaryDark },
  portrait: { width: 156, height: 210, alignItems: 'center', justifyContent: 'center', borderRadius: 78, borderWidth: 2, backgroundColor: colors.surface },
  placeholderFace: { width: 108, height: 142, alignItems: 'center', justifyContent: 'center', borderRadius: 54, opacity: 0.86 },
  initial: { color: '#FFFFFF', fontSize: 43, fontWeight: '900' },
  activityDot: { position: 'absolute', right: 14, bottom: 25, width: 14, height: 14, borderRadius: 7, borderWidth: 3, borderColor: colors.surface, backgroundColor: colors.muted },
  activityDotActive: { backgroundColor: colors.success },
  name: { marginTop: 12, color: colors.ink, fontSize: 18, fontWeight: '900' },
  activity: { marginTop: 4, color: colors.muted, fontSize: 11 },
  readyBadge: { marginTop: 13, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: colors.primarySoft },
  readyText: { color: colors.primaryDark, fontSize: 9, fontWeight: '800' },
});
