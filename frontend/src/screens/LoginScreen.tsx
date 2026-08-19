import { LinearGradient } from 'expo-linear-gradient';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { useAuth } from '../AuthContext';
import { shadow, useTheme, type ThemeColors } from '../theme';

export function LoginScreen() {
  const { colors, darkMode } = useTheme();
  const styles = createStyles(colors);
  const { login, register, notice, clearNotice } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (busy) return;

    clearNotice();
    const normalizedEmail = email.trim();
    const normalizedName = name.trim();

    if (!/^\S+@\S+\.\S+$/.test(normalizedEmail)) {
      setError('올바른 이메일 주소를 입력해 주세요.');
      return;
    }
    if (password.length < 8) {
      setError('비밀번호는 8자 이상 입력해 주세요.');
      return;
    }
    if (mode === 'register' && !normalizedName) {
      setError('이름을 입력해 주세요.');
      return;
    }

    setBusy(true);
    setError('');
    try {
      if (mode === 'login') {
        await login(normalizedEmail, password);
      } else {
        await register(normalizedEmail, password, normalizedName);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  const changeMode = (nextMode: 'login' | 'register') => {
    if (busy || nextMode === mode) return;
    setMode(nextMode);
    setError('');
    clearNotice();
  };

  return (
    <LinearGradient
      colors={darkMode ? ['#17131D', '#211B29', '#241A35'] : ['#F8F4FF', '#FFFFFF', '#F1EAFE']}
      style={styles.background}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.keyboard}
      >
        <View style={styles.content}>
          <View style={styles.brand}>
            <View style={styles.logo}>
              <Text style={styles.logoMark}>M</Text>
            </View>
            <Text style={styles.eyebrow}>나를 기억하는 대화 친구</Text>
            <Text style={styles.title}>MemoryPal</Text>
            <Text style={styles.subtitle}>말하는 순간부터, 소중한 기억이 이어져요.</Text>
          </View>

          <View style={styles.card}>
            <View style={styles.switcher}>
              {(['login', 'register'] as const).map((item) => (
                <Pressable
                  accessibilityRole="tab"
                  accessibilityState={{ selected: mode === item }}
                  disabled={busy}
                  key={item}
                  onPress={() => changeMode(item)}
                  style={[styles.switch, mode === item && styles.switchActive]}
                >
                  <Text style={[styles.switchText, mode === item && styles.switchTextActive]}>
                    {item === 'login' ? '로그인' : '회원가입'}
                  </Text>
                </Pressable>
              ))}
            </View>

            {mode === 'register' && (
              <View style={styles.field}>
                <Text style={styles.label}>이름</Text>
                <TextInput
                  autoComplete="name"
                  editable={!busy}
                  onChangeText={(value) => { setName(value); setError(''); }}
                  placeholder="어떻게 불러드릴까요?"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  value={name}
                />
              </View>
            )}

            <View style={styles.field}>
              <Text style={styles.label}>이메일</Text>
              <TextInput
                autoCapitalize="none"
                autoComplete="email"
                autoCorrect={false}
                editable={!busy}
                keyboardType="email-address"
                onChangeText={(value) => { setEmail(value); setError(''); }}
                placeholder="name@example.com"
                placeholderTextColor={colors.muted}
                style={styles.input}
                value={email}
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>비밀번호</Text>
              <TextInput
                autoCapitalize="none"
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                editable={!busy}
                onChangeText={(value) => { setPassword(value); setError(''); }}
                onSubmitEditing={() => { void submit(); }}
                placeholder="8자 이상 입력"
                placeholderTextColor={colors.muted}
                returnKeyType="done"
                secureTextEntry
                style={styles.input}
                value={password}
              />
            </View>

            {!!(error || notice) && (
              <Text accessibilityRole="alert" style={styles.error}>
                {error || notice}
              </Text>
            )}

            <Pressable
              accessibilityRole="button"
              disabled={busy}
              onPress={() => { void submit(); }}
              style={({ pressed }) => [
                styles.submit,
                busy ? styles.submitDisabled : undefined,
                pressed && !busy ? styles.submitPressed : undefined,
              ]}
            >
              {busy ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.submitText}>{mode === 'login' ? '로그인' : '회원가입'}</Text>
              )}
            </Pressable>

            <Text style={styles.privacy}>계정과 대화 세션은 분리되어 안전하게 관리돼요.</Text>
          </View>
        </View>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  background: { flex: 1 },
  keyboard: { flex: 1, justifyContent: 'center', padding: 24 },
  content: { width: '100%', maxWidth: 460, alignSelf: 'center' },
  brand: { alignItems: 'center', marginBottom: 28 },
  logo: {
    width: 62,
    height: 62,
    borderRadius: 22,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
    ...shadow,
  },
  logoMark: { color: '#FFFFFF', fontSize: 28, fontWeight: '900' },
  eyebrow: { color: colors.primaryDark, fontSize: 13, fontWeight: '700', letterSpacing: 1.4 },
  title: { color: colors.ink, fontSize: 36, fontWeight: '900', letterSpacing: -1.2, marginTop: 5 },
  subtitle: { color: colors.muted, fontSize: 14, marginTop: 7, textAlign: 'center' },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 28,
    padding: 22,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow,
  },
  switcher: { flexDirection: 'row', backgroundColor: colors.subtle, borderRadius: 14, padding: 4, marginBottom: 22 },
  switch: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 11 },
  switchActive: { backgroundColor: colors.surface },
  switchText: { color: colors.muted, fontSize: 14, fontWeight: '700' },
  switchTextActive: { color: colors.primaryDark },
  field: { marginBottom: 15 },
  label: { color: colors.ink, fontSize: 13, fontWeight: '700', marginBottom: 7 },
  input: {
    height: 52,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 14,
    paddingHorizontal: 15,
    color: colors.ink,
    backgroundColor: colors.input,
    fontSize: 15,
  },
  error: {
    color: colors.danger,
    backgroundColor: colors.dangerSoft,
    borderRadius: 12,
    padding: 12,
    marginBottom: 13,
    fontSize: 12,
    lineHeight: 18,
  },
  submit: {
    height: 54,
    borderRadius: 16,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 3,
  },
  submitDisabled: { opacity: 0.55 },
  submitPressed: { opacity: 0.82 },
  submitText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' },
  privacy: { color: colors.muted, fontSize: 11, textAlign: 'center', marginTop: 14 },
});
