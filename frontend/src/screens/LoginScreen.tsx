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
import { colors, shadow } from '../theme';

export function LoginScreen() {
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      if (mode === 'login') await login(email.trim(), password);
      else await register(email.trim(), password, name.trim());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '로그인하지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <LinearGradient colors={['#F8F4FF', '#FFFFFF', '#F1EAFE']} style={styles.background}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.keyboard}
      >
        <View style={styles.brand}>
          <View style={styles.logo}><Text style={styles.logoMark}>M</Text></View>
          <Text style={styles.eyebrow}>나를 기억하는 대화 친구</Text>
          <Text style={styles.title}>MemoryPal</Text>
          <Text style={styles.subtitle}>말하는 순간부터, 소중한 기억이 이어져요.</Text>
        </View>

        <View style={styles.card}>
          <View style={styles.switcher}>
            {(['login', 'register'] as const).map((item) => (
              <Pressable
                key={item}
                onPress={() => { setMode(item); setError(''); }}
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
                onChangeText={setName}
                placeholder="어떻게 불러드릴까요?"
                placeholderTextColor="#A49DAB"
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
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="hello@memorypal.app"
              placeholderTextColor="#A49DAB"
              style={styles.input}
              value={email}
            />
          </View>
          <View style={styles.field}>
            <Text style={styles.label}>비밀번호</Text>
            <TextInput
              autoCapitalize="none"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              onChangeText={setPassword}
              placeholder="8자 이상 입력해 주세요"
              placeholderTextColor="#A49DAB"
              secureTextEntry
              style={styles.input}
              value={password}
            />
          </View>
          {!!error && <Text style={styles.error}>{error}</Text>}
          <Pressable
            disabled={busy || !email || !password || (mode === 'register' && !name)}
            onPress={submit}
            style={({ pressed }) => [styles.submit, pressed && { opacity: 0.88 }, busy && { opacity: 0.6 }]}
          >
            {busy ? <ActivityIndicator color="#FFFFFF" /> : (
              <Text style={styles.submitText}>{mode === 'login' ? 'MemoryPal 시작하기' : '계정 만들기'}</Text>
            )}
          </Pressable>
          <Text style={styles.privacy}>계정과 대화 세션은 분리되어 안전하게 관리돼요.</Text>
        </View>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  background: { flex: 1 },
  keyboard: { flex: 1, justifyContent: 'center', padding: 24 },
  brand: { alignItems: 'center', marginBottom: 28 },
  logo: { width: 62, height: 62, borderRadius: 22, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginBottom: 18, ...shadow },
  logoMark: { color: '#FFFFFF', fontSize: 28, fontWeight: '900' },
  eyebrow: { color: colors.primaryDark, fontSize: 13, fontWeight: '700', letterSpacing: 1.4 },
  title: { color: colors.ink, fontSize: 36, fontWeight: '900', letterSpacing: -1.2, marginTop: 5 },
  subtitle: { color: colors.muted, fontSize: 14, marginTop: 7 },
  card: { backgroundColor: colors.surface, borderRadius: 28, padding: 22, borderWidth: 1, borderColor: '#F0ECF4', ...shadow },
  switcher: { flexDirection: 'row', backgroundColor: '#F5F2F7', borderRadius: 14, padding: 4, marginBottom: 22 },
  switch: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: 11 },
  switchActive: { backgroundColor: colors.surface },
  switchText: { color: colors.muted, fontSize: 14, fontWeight: '700' },
  switchTextActive: { color: colors.primaryDark },
  field: { marginBottom: 15 },
  label: { color: colors.ink, fontSize: 13, fontWeight: '700', marginBottom: 7 },
  input: { height: 52, borderWidth: 1, borderColor: colors.border, borderRadius: 14, paddingHorizontal: 15, color: colors.ink, backgroundColor: '#FEFDFE', fontSize: 15 },
  error: { color: colors.danger, marginBottom: 13, fontSize: 13 },
  submit: { height: 54, borderRadius: 16, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 3 },
  submitText: { color: '#FFFFFF', fontSize: 16, fontWeight: '800' },
  privacy: { color: colors.muted, fontSize: 11, textAlign: 'center', marginTop: 14 },
});

