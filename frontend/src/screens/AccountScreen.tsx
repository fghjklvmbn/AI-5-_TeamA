import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { useAuth } from '../AuthContext';
import { shadow, useTheme, type ThemeColors } from '../theme';
import type { User } from '../types';

type Props = {
  user: User;
  onClose: () => void;
};

function PasswordField({
  label,
  value,
  onChangeText,
  placeholder,
  autoComplete,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  autoComplete: 'current-password' | 'new-password';
}) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const [visible, setVisible] = useState(false);

  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.passwordField}>
        <TextInput
          autoCapitalize="none"
          autoComplete={autoComplete}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor={colors.muted}
          secureTextEntry={!visible}
          style={styles.passwordInput}
          value={value}
        />
        <Pressable accessibilityRole="button" onPress={() => setVisible((current) => !current)} style={styles.passwordToggle}>
          <Text style={styles.passwordToggleText}>{visible ? '숨기기' : '보기'}</Text>
        </Pressable>
      </View>
    </View>
  );
}

async function confirmAccountDeletion(): Promise<boolean> {
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    return window.confirm('탈퇴하면 계정 접근은 즉시 중지되고 연계 데이터는 삭제 절차에 따라 처리됩니다. 정말 탈퇴하시겠어요?');
  }
  return new Promise((resolve) => {
    Alert.alert(
      '정말 탈퇴하시겠어요?',
      '계정 접근은 즉시 중지되며 연계 데이터는 삭제 처리됩니다.',
      [
        { text: '취소', style: 'cancel', onPress: () => resolve(false) },
        { text: '회원탈퇴', style: 'destructive', onPress: () => resolve(true) },
      ],
      { cancelable: true, onDismiss: () => resolve(false) },
    );
  });
}

export function AccountScreen({ user, onClose }: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const { updateProfile, changePassword, deleteAccount } = useAuth();

  const [displayName, setDisplayName] = useState(user.display_name);
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [passwordError, setPasswordError] = useState('');

  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  useEffect(() => setDisplayName(user.display_name), [user.display_name]);

  const saveProfile = async () => {
    const nextName = displayName.trim();
    setProfileError('');
    setProfileSuccess('');
    if (!nextName) {
      setProfileError('닉네임을 입력해 주세요.');
      return;
    }
    if (nextName.length > 60) {
      setProfileError('닉네임은 60자 이하로 입력해 주세요.');
      return;
    }
    setProfileBusy(true);
    try {
      const updated = await updateProfile(nextName);
      setDisplayName(updated.display_name);
      setProfileSuccess('닉네임이 변경되었습니다.');
    } catch (reason) {
      setProfileError(reason instanceof Error ? reason.message : '닉네임을 변경하지 못했습니다.');
    } finally {
      setProfileBusy(false);
    }
  };

  const savePassword = async () => {
    setPasswordError('');
    if (!currentPassword) {
      setPasswordError('현재 비밀번호를 입력해 주세요.');
      return;
    }
    if (newPassword.length < 8) {
      setPasswordError('새 비밀번호는 8자 이상이어야 합니다.');
      return;
    }
    if (currentPassword === newPassword) {
      setPasswordError('현재 비밀번호와 다른 비밀번호를 사용해 주세요.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('새 비밀번호가 서로 일치하지 않습니다.');
      return;
    }
    setPasswordBusy(true);
    try {
      await changePassword(currentPassword, newPassword);
    } catch (reason) {
      setPasswordError(reason instanceof Error ? reason.message : '비밀번호를 변경하지 못했습니다.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordBusy(false);
    }
  };

  const removeAccount = async () => {
    setDeleteError('');
    if (!deletePassword) {
      setDeleteError('현재 비밀번호를 입력해 주세요.');
      return;
    }
    if (deleteConfirmation !== 'DELETE') {
      setDeleteError('확인란에 DELETE를 정확히 입력해 주세요.');
      return;
    }
    if (!await confirmAccountDeletion()) return;
    setDeleteBusy(true);
    try {
      await deleteAccount(deletePassword);
    } catch (reason) {
      setDeleteError(reason instanceof Error ? reason.message : '회원탈퇴를 처리하지 못했습니다.');
      setDeletePassword('');
      setDeleteConfirmation('');
      setDeleteBusy(false);
    }
  };

  const profileChanged = displayName.trim() !== user.display_name;
  const anyBusy = profileBusy || passwordBusy || deleteBusy;

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.keyboard}>
      <View style={styles.header}>
        <Pressable accessibilityLabel="계정 정보 닫기" accessibilityRole="button" disabled={anyBusy} onPress={onClose} style={styles.backButton}>
          <Text style={styles.backIcon}>‹</Text>
        </Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>MY ACCOUNT</Text>
          <Text style={styles.title}>계정 정보</Text>
        </View>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={styles.identityCard}>
          <View style={styles.avatar}><Text style={styles.avatarText}>{user.display_name.slice(0, 1)}</Text></View>
          <View style={styles.identityCopy}>
            <Text style={styles.identityName}>{user.display_name}</Text>
            <Text numberOfLines={1} style={styles.identityEmail}>{user.email}</Text>
          </View>
          <View style={styles.activeBadge}><View style={styles.activeDot} /><Text style={styles.activeText}>사용 중</Text></View>
        </View>

        <View style={styles.sectionCard}>
          <View style={styles.sectionHeader}>
            <View style={styles.sectionIcon}><Text style={styles.sectionIconText}>Aa</Text></View>
            <View><Text style={styles.sectionTitle}>닉네임</Text><Text style={styles.sectionDescription}>MemoryPal이 부르는 이름이에요.</Text></View>
          </View>
          <View style={styles.field}>
            <Text style={styles.label}>닉네임</Text>
            <TextInput
              autoComplete="name"
              maxLength={60}
              onChangeText={(value) => { setDisplayName(value); setProfileError(''); setProfileSuccess(''); }}
              placeholder="사용할 닉네임"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={displayName}
            />
            <Text style={styles.counter}>{displayName.length}/60</Text>
          </View>
          {!!profileError && <Text style={styles.errorText}>{profileError}</Text>}
          {!!profileSuccess && <Text style={styles.successText}>{profileSuccess}</Text>}
          <Pressable
            disabled={!profileChanged || profileBusy}
            onPress={() => void saveProfile()}
            style={({ pressed }) => [styles.primaryButton, (!profileChanged || profileBusy) && styles.buttonDisabled, pressed && styles.buttonPressed]}
          >
            {profileBusy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryButtonText}>변경사항 반영</Text>}
          </Pressable>
        </View>

        <View style={styles.sectionCard}>
          <View style={styles.sectionHeader}>
            <View style={styles.sectionIcon}><Text style={styles.lockIcon}>●</Text></View>
            <View><Text style={styles.sectionTitle}>비밀번호 변경</Text><Text style={styles.sectionDescription}>변경 후 모든 기기에서 다시 로그인해요.</Text></View>
          </View>
          <PasswordField autoComplete="current-password" label="현재 비밀번호" onChangeText={(value) => { setCurrentPassword(value); setPasswordError(''); }} placeholder="현재 비밀번호" value={currentPassword} />
          <PasswordField autoComplete="new-password" label="새 비밀번호" onChangeText={(value) => { setNewPassword(value); setPasswordError(''); }} placeholder="8자 이상 입력" value={newPassword} />
          <PasswordField autoComplete="new-password" label="새 비밀번호 확인" onChangeText={(value) => { setConfirmPassword(value); setPasswordError(''); }} placeholder="한 번 더 입력" value={confirmPassword} />
          {!!passwordError && <Text style={styles.errorText}>{passwordError}</Text>}
          <Pressable
            disabled={passwordBusy || !currentPassword || !newPassword || !confirmPassword}
            onPress={() => void savePassword()}
            style={({ pressed }) => [styles.secondaryButton, (passwordBusy || !currentPassword || !newPassword || !confirmPassword) && styles.buttonDisabled, pressed && styles.buttonPressed]}
          >
            {passwordBusy ? <ActivityIndicator color={colors.primaryDark} /> : <Text style={styles.secondaryButtonText}>비밀번호 변경</Text>}
          </Pressable>
        </View>

        <View style={[styles.sectionCard, styles.dangerCard]}>
          <View style={styles.sectionHeader}>
            <View style={styles.dangerIcon}><Text style={styles.dangerIconText}>!</Text></View>
            <View style={styles.sectionHeaderCopy}><Text style={styles.dangerTitle}>회원탈퇴</Text><Text style={styles.sectionDescription}>탈퇴 후에는 계정에 다시 접근할 수 없어요.</Text></View>
          </View>
          <View style={styles.dangerNotice}>
            <Text style={styles.dangerNoticeTitle}>탈퇴 전에 확인해 주세요</Text>
            <Text style={styles.dangerNoticeText}>계정 접근은 즉시 중지되고, 대화·기억·개인화 정보 등 연계 데이터는 삭제 절차에 따라 처리됩니다.</Text>
          </View>
          <PasswordField autoComplete="current-password" label="현재 비밀번호" onChangeText={(value) => { setDeletePassword(value); setDeleteError(''); }} placeholder="본인 확인을 위해 입력" value={deletePassword} />
          <View style={styles.field}>
            <Text style={styles.label}>확인 문구</Text>
            <TextInput
              autoCapitalize="characters"
              onChangeText={(value) => { setDeleteConfirmation(value); setDeleteError(''); }}
              placeholder="DELETE 입력"
              placeholderTextColor={colors.muted}
              style={[styles.input, styles.dangerInput]}
              value={deleteConfirmation}
            />
          </View>
          {!!deleteError && <Text style={styles.errorText}>{deleteError}</Text>}
          <Pressable
            disabled={deleteBusy || !deletePassword || deleteConfirmation !== 'DELETE'}
            onPress={() => void removeAccount()}
            style={({ pressed }) => [styles.deleteButton, (deleteBusy || !deletePassword || deleteConfirmation !== 'DELETE') && styles.buttonDisabled, pressed && styles.buttonPressed]}
          >
            {deleteBusy ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.deleteButtonText}>계정 영구 삭제</Text>}
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  keyboard: { flex: 1, backgroundColor: colors.background },
  header: { minHeight: 78, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: colors.border, paddingHorizontal: 18, paddingVertical: 12, backgroundColor: colors.surface },
  backButton: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center', borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.subtle },
  backIcon: { color: colors.ink, fontSize: 32, lineHeight: 34, fontWeight: '400', marginTop: -3 },
  headerCopy: { flex: 1, alignItems: 'center' },
  headerSpacer: { width: 42 },
  eyebrow: { color: colors.primaryDark, fontSize: 9, fontWeight: '900', letterSpacing: 1.6 },
  title: { color: colors.ink, fontSize: 20, fontWeight: '900', marginTop: 3 },
  content: { padding: 18, paddingBottom: 42, gap: 14 },
  identityCard: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 17, borderRadius: 22, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, ...shadow },
  avatar: { width: 48, height: 48, alignItems: 'center', justifyContent: 'center', borderRadius: 17, backgroundColor: colors.primarySoft },
  avatarText: { color: colors.primaryDark, fontSize: 20, fontWeight: '900' },
  identityCopy: { flex: 1, minWidth: 0 },
  identityName: { color: colors.ink, fontSize: 16, fontWeight: '900' },
  identityEmail: { color: colors.muted, fontSize: 11, marginTop: 4 },
  activeBadge: { flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 99, backgroundColor: colors.primarySoft, paddingHorizontal: 9, paddingVertical: 6 },
  activeDot: { width: 6, height: 6, borderRadius: 99, backgroundColor: colors.success },
  activeText: { color: colors.primaryDark, fontSize: 9, fontWeight: '800' },
  sectionCard: { borderRadius: 22, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 11, marginBottom: 19 },
  sectionHeaderCopy: { flex: 1 },
  sectionIcon: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center', borderRadius: 13, backgroundColor: colors.primarySoft },
  sectionIconText: { color: colors.primaryDark, fontSize: 12, fontWeight: '900' },
  lockIcon: { color: colors.primaryDark, fontSize: 13, fontWeight: '900' },
  sectionTitle: { color: colors.ink, fontSize: 15, fontWeight: '900' },
  sectionDescription: { color: colors.muted, fontSize: 10, lineHeight: 15, marginTop: 3 },
  field: { marginBottom: 14, position: 'relative' },
  label: { color: colors.ink, fontSize: 12, fontWeight: '800', marginBottom: 7 },
  input: { height: 50, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.input, color: colors.ink, fontSize: 14, paddingHorizontal: 14 },
  counter: { position: 'absolute', right: 12, bottom: -13, color: colors.muted, fontSize: 9 },
  passwordField: { height: 50, flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.input },
  passwordInput: { flex: 1, height: '100%', color: colors.ink, fontSize: 14, paddingHorizontal: 14 },
  passwordToggle: { height: '100%', justifyContent: 'center', paddingHorizontal: 14 },
  passwordToggleText: { color: colors.primaryDark, fontSize: 10, fontWeight: '900' },
  errorText: { color: colors.danger, backgroundColor: colors.dangerSoft, borderRadius: 10, paddingHorizontal: 11, paddingVertical: 9, fontSize: 11, lineHeight: 16, marginBottom: 11 },
  successText: { color: colors.success, backgroundColor: colors.primarySoft, borderRadius: 10, paddingHorizontal: 11, paddingVertical: 9, fontSize: 11, lineHeight: 16, marginBottom: 11 },
  primaryButton: { height: 50, alignItems: 'center', justifyContent: 'center', borderRadius: 15, backgroundColor: colors.primary, marginTop: 4 },
  primaryButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '900' },
  secondaryButton: { height: 50, alignItems: 'center', justifyContent: 'center', borderRadius: 15, borderWidth: 1, borderColor: colors.lilac, backgroundColor: colors.primarySoft, marginTop: 4 },
  secondaryButtonText: { color: colors.primaryDark, fontSize: 14, fontWeight: '900' },
  buttonDisabled: { opacity: 0.43 },
  buttonPressed: { opacity: 0.78 },
  dangerCard: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  dangerIcon: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center', borderRadius: 13, backgroundColor: colors.danger },
  dangerIconText: { color: '#FFFFFF', fontSize: 18, fontWeight: '900' },
  dangerTitle: { color: colors.danger, fontSize: 15, fontWeight: '900' },
  dangerNotice: { borderRadius: 14, backgroundColor: colors.surface, padding: 13, marginBottom: 16, borderWidth: 1, borderColor: colors.border },
  dangerNoticeTitle: { color: colors.danger, fontSize: 11, fontWeight: '900' },
  dangerNoticeText: { color: colors.muted, fontSize: 10, lineHeight: 16, marginTop: 5 },
  dangerInput: { borderColor: colors.danger },
  deleteButton: { height: 50, alignItems: 'center', justifyContent: 'center', borderRadius: 15, backgroundColor: colors.danger, marginTop: 3 },
  deleteButtonText: { color: '#FFFFFF', fontSize: 14, fontWeight: '900' },
});
