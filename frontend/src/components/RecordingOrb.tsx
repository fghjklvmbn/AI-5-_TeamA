import { LinearGradient } from 'expo-linear-gradient';
import React, { useEffect, useRef } from 'react';
import { Animated, Pressable, StyleSheet, Text, View } from 'react-native';

import { shadow, useTheme, type ThemeColors } from '../theme';

type Props = {
  recording: boolean;
  amplitude: number;
  disabled?: boolean;
  onPress: () => void;
};

export function RecordingOrb({ recording, amplitude, disabled, onPress }: Props) {
  const { colors, darkMode } = useTheme();
  const styles = createStyles(colors);
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!recording) {
      pulse.stopAnimation();
      pulse.setValue(0);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1150, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 1150, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse, recording]);

  const outerScale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.22 + amplitude * 0.12] });
  return (
    <View style={styles.wrap}>
      {recording && (
        <>
          <Animated.View style={[styles.ring, styles.ringOuter, { transform: [{ scale: outerScale }] }]} />
          <Animated.View
            style={[
              styles.ring,
              styles.ringInner,
              { transform: [{ scale: 1.02 + amplitude * 0.18 }], opacity: 0.35 + amplitude * 0.35 },
            ]}
          />
        </>
      )}
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={recording ? '녹음 중지' : '음성 대화 시작'}
        disabled={disabled}
        onPress={onPress}
        style={({ pressed }) => [styles.button, pressed && styles.pressed, disabled && styles.disabled]}
      >
        <LinearGradient
          colors={recording ? ['#8F6EE8', '#6842CC'] : darkMode ? ['#453661', '#302641'] : ['#F3EEFF', '#DCD0FB']}
          style={styles.gradient}
        >
          <Text style={[styles.mic, recording && styles.micActive]}>{recording ? '■' : '●'}</Text>
          <Text style={[styles.label, recording && styles.labelActive]}>
            {recording ? '듣고 있어요' : '시작하기'}
          </Text>
        </LinearGradient>
      </Pressable>
    </View>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  wrap: { width: 296, height: 296, alignItems: 'center', justifyContent: 'center' },
  ring: { position: 'absolute', width: 236, height: 236, borderRadius: 999 },
  ringOuter: { backgroundColor: colors.primarySoft, opacity: 0.55 },
  ringInner: { backgroundColor: colors.lilac },
  button: { width: 208, height: 208, borderRadius: 999, overflow: 'hidden', ...shadow },
  pressed: { transform: [{ scale: 0.97 }] },
  disabled: { opacity: 0.55 },
  gradient: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 8 },
  mic: { color: colors.primaryDark, fontSize: 29, lineHeight: 34 },
  micActive: { color: '#FFFFFF', fontSize: 20 },
  label: { color: colors.ink, fontSize: 16, fontWeight: '700' },
  labelActive: { color: '#FFFFFF' },
});

