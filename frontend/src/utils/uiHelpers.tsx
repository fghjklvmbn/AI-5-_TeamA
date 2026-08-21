import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';

/**
 * 에러 표시 컴포넌트
 */
export interface ErrorViewProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorView({ message, onRetry }: ErrorViewProps) {
  const { colors } = useTheme();
  const styles = createStyles(colors);

  return (
    <View style={styles.container}>
      <View style={[styles.errorBox, styles.errorPrimary]}>
        <Text style={styles.errorIcon}>⚠️</Text>
        <Text style={styles.errorText}>{message}</Text>
      </View>
      
      {onRetry && (
        <View style={styles.retryContainer}>
          <Text style={styles.retryLabel}>다시 시도하기</Text>
          <Text style={styles.retrySubtext}>(클릭)</Text>
          <Pressable onPress={onRetry} style={styles.retryButton}>
            <Text style={styles.retryButtonText}>재시도</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

/**
 * 로딩 표시 컴포넌트
 */
export interface LoadingViewProps {
  message?: string;
  progress?: number | null;
}

export function LoadingView({ message, progress }: LoadingViewProps) {
  const { colors } = useTheme();
  const styles = createStyles(colors);

  return (
    <View style={styles.container}>
      <View style={styles.loadingBox}>
        <ActivityIndicator testID="loading-indicator" size="large" color={colors.primary} />
        
        {message && (
          <Text style={styles.loadingText}>{message}</Text>
        )}
        
        {progress !== null && progress !== undefined && (
          <View style={styles.progressContainer}>
            <View
              testID="progress-bar"
              style={[styles.progressBar, { width: `${Math.min(100, Math.max(0, progress))}%` }]} 
            />
          </View>
        )}
      </View>
    </View>
  );
}

/**
 * 성공 메시지 표시 컴포넌트
 */
export interface SuccessViewProps {
  message: string;
  onContinue?: () => void;
}

export function SuccessView({ message, onContinue }: SuccessViewProps) {
  const { colors } = useTheme();
  const styles = createStyles(colors);

  return (
    <View style={styles.container}>
      <View style={[styles.successBox, styles.successPrimary]}>
        <Text style={styles.successIcon}>✅</Text>
        <Text style={styles.successText}>{message.trim()}</Text>
      </View>
      
      {onContinue && (
        <Pressable onPress={onContinue} style={styles.continueButton}>
          <Text style={styles.continueButtonText}>계속하기</Text>
        </Pressable>
      )}
    </View>
  );
}

/**
 * 확인 다이얼로그 컴포넌트
 */
export interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
  variant?: 'default' | 'danger';
}

export function ConfirmDialog({
  title,
  message,
  confirmLabel = '확인',
  cancelLabel = '취소',
  onConfirm,
  onCancel,
  variant = 'default',
}: ConfirmDialogProps) {
  const { colors } = useTheme();
  const styles = createStyles(colors);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      
      <View style={[styles.buttonContainer, variant === 'danger' && styles.dangerButtonContainer]}>
        <Pressable 
          onPress={() => { onConfirm(); onCancel(); }}
          style={styles.confirmButton}
          accessibilityRole="button"
          accessibilityLabel={confirmLabel}
        >
          <Text style={[styles.confirmButtonText, variant === 'danger' && styles.dangerConfirmText]}>
            {confirmLabel}
          </Text>
        </Pressable>
        
        <Pressable 
          onPress={onCancel}
          style={styles.cancelButton}
          accessibilityRole="button"
          accessibilityLabel={cancelLabel}
        >
          <Text style={styles.cancelButtonText}>{cancelLabel}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  container: { padding: 16, flex: 1 },
  
  // 에러 스타일
  errorBox: { backgroundColor: '#FFF3CD', padding: 12, borderRadius: 8, marginBottom: 12 },
  errorPrimary: { backgroundColor: '#F8F4FF' },
  errorIcon: { fontSize: 24, fontWeight: 'bold' },
  errorText: { color: '#666', fontSize: 14, textAlign: 'center', marginTop: 4 },
  
  // 성공 스타일
  successBox: { backgroundColor: '#D4EDDA', padding: 12, borderRadius: 8, marginBottom: 12 },
  successPrimary: { backgroundColor: '#DCF8C6' },
  successIcon: { fontSize: 24, fontWeight: 'bold' },
  successText: { color: '#155724', fontSize: 14, textAlign: 'center', marginTop: 4 },
  
  // 로딩 스타일
  loadingBox: { alignItems: 'center' },
  loadingText: { color: '#666', fontSize: 14, marginTop: 8 },
  progressContainer: { width: 200, height: 8, backgroundColor: '#E9ECEF', borderRadius: 4, marginTop: 8, overflow: 'hidden' },
  progressBar: { height: '100%', backgroundColor: colors.primary },
  
  // 버튼 스타일
  buttonContainer: { flexDirection: 'row', gap: 8 },
  dangerButtonContainer: { justifyContent: 'flex-end' },
  confirmButton: { flex: 1, backgroundColor: colors.primary, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  cancelButton: { flex: 1, backgroundColor: '#E9ECEF', paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  
  // 버튼 텍스트
  confirmButtonText: { color: colors.surface, fontWeight: '600' },
  cancelButtonText: { color: colors.ink, fontWeight: '600' },
  dangerConfirmText: { color: '#DC3545' },
  
  retryContainer: { flexDirection: 'row', justifyContent: 'center', gap: 8, marginTop: 12 },
  retryLabel: { color: colors.ink, fontSize: 12 },
  retrySubtext: { color: colors.muted, fontSize: 10 },
  retryButton: { backgroundColor: colors.primarySoft, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 16 },
  retryButtonText: { color: colors.primaryDark, fontWeight: '600', fontSize: 14 },
  
  continueButton: { backgroundColor: colors.primary, paddingVertical: 12, borderRadius: 8, alignItems: 'center' },
  continueButtonText: { color: colors.surface, fontWeight: '600', fontSize: 16 },
  
  title: { textAlign: 'center', fontSize: 18, fontWeight: 'bold', color: colors.ink, marginBottom: 8 },
  message: { textAlign: 'center', fontSize: 14, color: colors.muted, marginBottom: 16 },
});
