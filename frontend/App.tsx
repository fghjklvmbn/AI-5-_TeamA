import AsyncStorage from '@react-native-async-storage/async-storage';
import { BlurView } from 'expo-blur';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from './src/AuthContext';
import { BottomTabs, type Tab } from './src/components/BottomTabs';
import { ChatScreen } from './src/screens/ChatScreen';
import { AccountScreen } from './src/screens/AccountScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { LoginScreen } from './src/screens/LoginScreen';
import { MemoryScreen } from './src/screens/MemoryScreen';
import { PortraitScreen } from './src/screens/PortraitScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { ThemeProvider, useTheme } from './src/theme';
import type { ChatResponse, Message, Persona, ReasoningEffort } from './src/types';

function MemoryPalApp({ darkMode, onDarkModeChange }: { darkMode: boolean; onDarkModeChange: (enabled: boolean) => void }) {
  const { loading, token, user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>('home');
  const [sessionId, setSessionId] = useState<string>();
  const [casualMode, setCasualMode] = useState(false);
  const [persona, setPersona] = useState<Persona>('default');
  const [voiceReplyEnabled, setVoiceReplyEnabled] = useState(true);
  const [internetEnabled, setInternetEnabled] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('medium');
  const [voiceProcessing, setVoiceProcessing] = useState<{ active: boolean; transcript: string }>({ active: false, transcript: '' });
  const [incomingMessage, setIncomingMessage] = useState<Message>();
  const [accountOpen, setAccountOpen] = useState(false);
  const { colors } = useTheme();
  const styles = createStyles(colors);

  useEffect(() => {
    if (!user) {
      setAccountOpen(false);
      setCasualMode(false);
      setPersona('default');
      setVoiceReplyEnabled(true);
      setInternetEnabled(false);
      setThinkingMode(false);
      setReasoningEffort('medium');
      return;
    }
    let active = true;
    setReasoningEffort('medium');
    void AsyncStorage.getItem(`memorypal.casualMode.${user.id}`).then((stored) => {
      if (active) setCasualMode(stored === 'true');
    });
    void AsyncStorage.getItem(`memorypal.persona.${user.id}`).then((stored) => {
      if (active && (stored === 'default' || stored === 'emotional_companion')) {
        setPersona(stored);
      }
    });
    void AsyncStorage.getItem(`memorypal.voiceReplyEnabled.${user.id}`).then((stored) => {
      if (active) setVoiceReplyEnabled(stored !== 'false');
    });
    void AsyncStorage.getItem(`memorypal.internetEnabled.${user.id}`).then((stored) => {
      if (active) setInternetEnabled(stored === 'true');
    });
    void AsyncStorage.getItem(`memorypal.thinkingMode.${user.id}`).then((stored) => {
      if (active) setThinkingMode(stored === 'true');
    });
    void AsyncStorage.getItem(`memorypal.reasoningEffort.${user.id}`).then((stored) => {
      if (active && (stored === 'low' || stored === 'medium' || stored === 'high')) {
        setReasoningEffort(stored);
      }
    });
    return () => { active = false; };
  }, [user]);

  if (loading) {
    return <View style={styles.loading}><ActivityIndicator color={colors.primary} size="large" /></View>;
  }
  if (!token || !user) return <LoginScreen />;

  const openVoiceConversation = (response: ChatResponse) => {
    setSessionId(response.session.id);
    setIncomingMessage(response.message);
    setTab('chat');
  };

  const updateConversation = (id: string) => {
    setSessionId(id || undefined);
  };

  const updateCasualMode = (enabled: boolean) => {
    setCasualMode(enabled);
    void AsyncStorage.setItem(`memorypal.casualMode.${user.id}`, String(enabled));
  };

  const updatePersona = (value: Persona) => {
    setPersona(value);
    void AsyncStorage.setItem(`memorypal.persona.${user.id}`, value);
  };

  const updateVoiceReply = (enabled: boolean) => {
    setVoiceReplyEnabled(enabled);
    void AsyncStorage.setItem(`memorypal.voiceReplyEnabled.${user.id}`, String(enabled));
  };

  const updateInternetEnabled = (enabled: boolean) => {
    setInternetEnabled(enabled);
    void AsyncStorage.setItem(`memorypal.internetEnabled.${user.id}`, String(enabled));
  };

  const updateThinkingMode = (enabled: boolean) => {
    setThinkingMode(enabled);
    void AsyncStorage.setItem(`memorypal.thinkingMode.${user.id}`, String(enabled));
  };

  const updateReasoningEffort = (effort: ReasoningEffort) => {
    setReasoningEffort(effort);
    void AsyncStorage.setItem(`memorypal.reasoningEffort.${user.id}`, effort);
  };

  const updateDarkMode = (enabled: boolean) => {
    onDarkModeChange(enabled);
    void AsyncStorage.setItem('memorypal.darkMode', String(enabled));
  };

  const updateVoiceProcessing = (active: boolean, transcript = '') => {
    setVoiceProcessing({ active, transcript: active ? transcript : '' });
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style={darkMode ? 'light' : 'dark'} />
      <View style={styles.phone}>
        {accountOpen ? (
          <AccountScreen user={user} onClose={() => setAccountOpen(false)} />
        ) : (<>
        <View style={styles.screen}>
          {tab === 'home' && <HomeScreen token={token} user={user} casualMode={casualMode} persona={persona} voiceReplyEnabled={voiceReplyEnabled} internetEnabled={internetEnabled} thinkingMode={thinkingMode} reasoningEffort={reasoningEffort} onPersonaChange={updatePersona} onConversation={openVoiceConversation} onVoiceProcessingChange={updateVoiceProcessing} onOpenAccount={() => setAccountOpen(true)} onLogout={logout} />}
          <View
            pointerEvents={tab === 'chat' ? 'auto' : 'none'}
            style={[styles.chatScreen, tab !== 'chat' && styles.hiddenScreen]}
          >
            <ChatScreen
              token={token}
              activeSessionId={sessionId}
              casualMode={casualMode}
              persona={persona}
              voiceReplyEnabled={voiceReplyEnabled}
              internetEnabled={internetEnabled}
              thinkingMode={thinkingMode}
              reasoningEffort={reasoningEffort}
              incomingMessage={incomingMessage}
              onIncomingMessageConsumed={() => setIncomingMessage(undefined)}
              onSessionChange={updateConversation}
              onVoiceProcessingChange={updateVoiceProcessing}
            />
          </View>
          {tab === 'memory' && <MemoryScreen token={token} />}
          <View
            pointerEvents={tab === 'portrait' ? 'auto' : 'none'}
            style={[styles.portraitScreen, tab !== 'portrait' && styles.hiddenScreen]}
          >
            <PortraitScreen token={token} persona={persona} />
          </View>
          {tab === 'settings' && <SettingsScreen token={token} user={user} casualMode={casualMode} persona={persona} darkMode={darkMode} voiceReplyEnabled={voiceReplyEnabled} internetEnabled={internetEnabled} thinkingMode={thinkingMode} reasoningEffort={reasoningEffort} onCasualModeChange={updateCasualMode} onPersonaChange={updatePersona} onDarkModeChange={updateDarkMode} onVoiceReplyChange={updateVoiceReply} onInternetEnabledChange={updateInternetEnabled} onThinkingModeChange={updateThinkingMode} onReasoningEffortChange={updateReasoningEffort} onOpenAccount={() => setAccountOpen(true)} logout={logout} />}
        </View>
        <BottomTabs current={tab} onChange={setTab} />
        </>)}
      </View>
      {voiceProcessing.active && (
        <View style={styles.processingOverlay}>
          <BlurView intensity={32} style={StyleSheet.absoluteFill} tint={darkMode ? 'dark' : 'light'} />
          <View style={styles.processingShade} />
          <View style={styles.processingCard}>
            <ActivityIndicator color={colors.primary} size="large" />
            <Text style={styles.processingTitle}>
              {voiceProcessing.transcript ? '답변을 준비하고 있어요' : '음성을 인식하고 있어요'}
            </Text>
            <Text style={styles.processingDescription}>잠시만 기다려 주세요.</Text>
            {!!voiceProcessing.transcript && (
              <View style={styles.transcriptPreview}>
                <Text style={styles.transcriptLabel}>인식된 내용</Text>
                <Text style={styles.transcriptText}>{voiceProcessing.transcript}</Text>
              </View>
            )}
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

export default function App() {
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    void AsyncStorage.getItem('memorypal.darkMode').then((stored) => setDarkMode(stored === 'true'));
  }, []);

  return (
    <ThemeProvider darkMode={darkMode}>
      <SafeAreaProvider><AuthProvider><MemoryPalApp darkMode={darkMode} onDarkModeChange={setDarkMode} /></AuthProvider></SafeAreaProvider>
    </ThemeProvider>
  );
}

const createStyles = (colors: import('./src/theme').ThemeColors) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background, alignItems: 'center' },
  phone: { flex: 1, width: '100%', maxWidth: 560, backgroundColor: colors.background },
  screen: { flex: 1 },
  chatScreen: { flex: 1 },
  portraitScreen: { flex: 1 },
  hiddenScreen: { display: 'none' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background },
  processingOverlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, zIndex: 100, elevation: 100, alignItems: 'center', justifyContent: 'center', padding: 24 },
  processingShade: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(15, 10, 22, 0.48)' },
  processingCard: { width: '100%', maxWidth: 440, alignItems: 'center', borderRadius: 26, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, paddingHorizontal: 24, paddingVertical: 28 },
  processingTitle: { color: colors.ink, fontSize: 19, fontWeight: '900', marginTop: 16 },
  processingDescription: { color: colors.muted, fontSize: 12, marginTop: 6 },
  transcriptPreview: { width: '100%', marginTop: 20, borderRadius: 18, backgroundColor: colors.primarySoft, padding: 16 },
  transcriptLabel: { color: colors.primaryDark, fontSize: 10, fontWeight: '900', marginBottom: 7 },
  transcriptText: { color: colors.ink, fontSize: 15, lineHeight: 22, fontWeight: '600' },
});
