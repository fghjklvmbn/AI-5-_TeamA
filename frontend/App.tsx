import AsyncStorage from '@react-native-async-storage/async-storage';
import { BlurView } from 'expo-blur';
import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Alert, StyleSheet, Text, View } from 'react-native';
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
import { api } from './src/api';
import { DEFAULT_CHARACTER_ID, isCharacterId } from './src/character/ids';
import type { CharacterId, ChatResponse, ConversationMode, Message, ModelReasoningCapabilities, Persona, ReasoningEffort } from './src/types';

function persistPreference(task: Promise<void>): void {
  void task.catch(() => undefined);
}

function MemoryPalApp({ darkMode, onDarkModeChange }: { darkMode: boolean; onDarkModeChange: (enabled: boolean) => void }) {
  const { loading, token, user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>('home');
  const [sessionId, setSessionId] = useState<string>();
  const [casualMode, setCasualMode] = useState(false);
  const [persona, setPersona] = useState<Persona>('default');
  const [personaLoading, setPersonaLoading] = useState<Persona>();
  const [voiceId, setVoiceId] = useState<string>();
  const [voiceReplyEnabled, setVoiceReplyEnabled] = useState(true);
  const [internetEnabled, setInternetEnabled] = useState(false);
  const [thinkingMode, setThinkingMode] = useState(false);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('medium');
  const [modelCapabilities, setModelCapabilities] = useState<ModelReasoningCapabilities>();
  const [modelCapabilitiesLoading, setModelCapabilitiesLoading] = useState(false);
  const [selectedModelKey, setSelectedModelKey] = useState<string>();
  const [conversationMode, setConversationMode] = useState<ConversationMode>('chat');
  const [characterId, setCharacterId] = useState<CharacterId>(DEFAULT_CHARACTER_ID);
  const [voiceProcessing, setVoiceProcessing] = useState<{ active: boolean; transcript: string }>({ active: false, transcript: '' });
  const [incomingMessage, setIncomingMessage] = useState<Message>();
  const [accountOpen, setAccountOpen] = useState(false);
  const { colors } = useTheme();
  const styles = createStyles(colors);

  const openVoiceConversation = useCallback((response: ChatResponse) => {
    setSessionId(response.session.id);
    setIncomingMessage(response.message);
    setTab('chat');
  }, []);

  const updateConversation = useCallback((id: string) => {
    setSessionId(id || undefined);
  }, []);

  const updateVoiceProcessing = useCallback((active: boolean, transcript = '') => {
    setVoiceProcessing({ active, transcript: active ? transcript : '' });
  }, []);

  const consumeIncomingMessage = useCallback(() => setIncomingMessage(undefined), []);

  useEffect(() => {
    if (!user || !token) {
      setTab('home');
      setSessionId(undefined);
      setIncomingMessage(undefined);
      setVoiceProcessing({ active: false, transcript: '' });
      setAccountOpen(false);
      setCasualMode(false);
      setPersona('default');
      setPersonaLoading(undefined);
      setVoiceId(undefined);
      setVoiceReplyEnabled(true);
      setInternetEnabled(false);
      setThinkingMode(false);
      setReasoningEffort('medium');
      setSelectedModelKey(undefined);
      setConversationMode('chat');
      setCharacterId(DEFAULT_CHARACTER_ID);
      return;
    }
    let active = true;
    setTab('home');
    setSessionId(undefined);
    setIncomingMessage(undefined);
    setVoiceProcessing({ active: false, transcript: '' });
    setVoiceId(undefined);
    setReasoningEffort('medium');
    void AsyncStorage.getItem(`memorypal.casualMode.${user.id}`).then((stored) => {
      if (active) setCasualMode(stored === 'true');
    }).catch(() => undefined);
    void AsyncStorage.getItem(`memorypal.persona.${user.id}`).then((stored) => {
      if (active && (stored === 'default' || stored === 'emotional_companion' || stored === 'none')) {
        setPersona(stored);
      }
    }).catch(() => undefined);
    void AsyncStorage.getItem(`memorypal.voiceReplyEnabled.${user.id}`).then((stored) => {
      if (active) setVoiceReplyEnabled(stored !== 'false');
    }).catch(() => undefined);
    void AsyncStorage.getItem(`memorypal.internetEnabled.${user.id}`).then((stored) => {
      if (active) setInternetEnabled(stored === 'true');
    }).catch(() => undefined);
    void AsyncStorage.getItem(`memorypal.thinkingMode.${user.id}`).then((stored) => {
      if (active) setThinkingMode(stored === 'true');
    }).catch(() => undefined);
    void AsyncStorage.getItem(`memorypal.reasoningEffort.${user.id}`).then((stored) => {
      if (active && (stored === 'low' || stored === 'medium' || stored === 'high')) {
        setReasoningEffort(stored);
      }
    }).catch(() => undefined);
    void api.modelSelection(token).then((selection) => {
      if (!active) return;
      const selected = selection.model_key || undefined;
      setSelectedModelKey(selected);
      const key = `memorypal.selectedModel.${user.id}`;
      persistPreference(selected ? AsyncStorage.setItem(key, selected) : AsyncStorage.removeItem(key));
    }).catch(() => {
      void AsyncStorage.getItem(`memorypal.selectedModel.${user.id}`).then((stored) => {
        if (active) setSelectedModelKey(stored || undefined);
      }).catch(() => undefined);
    });
    void AsyncStorage.getItem(`memorypal.conversationMode.${user.id}`).then((stored) => {
      if (active && (stored === 'live' || stored === 'chat' || stored === 'hybrid')) setConversationMode(stored);
    }).catch(() => undefined);
    void AsyncStorage.getItem(`memorypal.characterId.${user.id}`).then((stored) => {
      if (active && isCharacterId(stored)) setCharacterId(stored);
    }).catch(() => undefined);
    return () => { active = false; };
  }, [token, user?.id]);

  useEffect(() => {
    if (!token || !user) {
      setModelCapabilities(undefined);
      setModelCapabilitiesLoading(false);
      return;
    }
    const controller = new AbortController();
    setModelCapabilities(undefined);
    setModelCapabilitiesLoading(true);
    void api.modelCapabilities(token, persona, controller.signal, selectedModelKey).then((capabilities) => {
      if (controller.signal.aborted) return;
      setModelCapabilities(capabilities);
      if (!capabilities.thinking_supported) {
        setThinkingMode(false);
        persistPreference(AsyncStorage.setItem(`memorypal.thinkingMode.${user.id}`, 'false'));
      }
      if (
        capabilities.reasoning_efforts.length
        && !capabilities.reasoning_efforts.includes(reasoningEffort)
      ) {
        const preferred = capabilities.default_reasoning;
        const next = preferred && capabilities.reasoning_efforts.includes(preferred as ReasoningEffort)
          ? preferred as ReasoningEffort
          : capabilities.reasoning_efforts[0] ?? 'medium';
        setReasoningEffort(next);
        persistPreference(AsyncStorage.setItem(`memorypal.reasoningEffort.${user.id}`, next));
      }
    }).catch(() => {
      if (!controller.signal.aborted) setModelCapabilities(undefined);
    }).finally(() => {
      if (!controller.signal.aborted) setModelCapabilitiesLoading(false);
    });
    return () => controller.abort();
  }, [persona, selectedModelKey, token, user?.id]);

  useEffect(() => {
    if (!user || persona !== 'emotional_companion') return;
    setThinkingMode(false);
    persistPreference(AsyncStorage.setItem(`memorypal.thinkingMode.${user.id}`, 'false'));
  }, [persona, user?.id]);

  if (loading) {
    return <View style={styles.loading}><ActivityIndicator color={colors.primary} size="large" /></View>;
  }
  if (!token || !user) return <LoginScreen />;

  const updateCasualMode = (enabled: boolean) => {
    setCasualMode(enabled);
    persistPreference(AsyncStorage.setItem(`memorypal.casualMode.${user.id}`, String(enabled)));
  };

  const updatePersona = async (value: Persona) => {
    if (personaLoading) return;
    setPersonaLoading(value);
    try {
      const selection = await api.activatePersona(token, value);
      setPersona(value);
      if (value !== 'emotional_companion') {
        setSelectedModelKey(selection.model_key || undefined);
      }
      persistPreference(AsyncStorage.setItem(`memorypal.persona.${user.id}`, value));
    } catch (reason) {
      Alert.alert(
        '페르소나 전환 실패',
        reason instanceof Error ? reason.message : '모델을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.',
      );
    } finally {
      setPersonaLoading(undefined);
    }
  };

  const updateVoiceReply = (enabled: boolean) => {
    setVoiceReplyEnabled(enabled);
    persistPreference(AsyncStorage.setItem(`memorypal.voiceReplyEnabled.${user.id}`, String(enabled)));
  };

  const updateInternetEnabled = (enabled: boolean) => {
    setInternetEnabled(enabled);
    persistPreference(AsyncStorage.setItem(`memorypal.internetEnabled.${user.id}`, String(enabled)));
  };

  const updateThinkingMode = (enabled: boolean) => {
    setThinkingMode(enabled);
    persistPreference(AsyncStorage.setItem(`memorypal.thinkingMode.${user.id}`, String(enabled)));
  };

  const updateReasoningEffort = (effort: ReasoningEffort) => {
    setReasoningEffort(effort);
    persistPreference(AsyncStorage.setItem(`memorypal.reasoningEffort.${user.id}`, effort));
  };

  const updateSelectedModel = (modelKey: string | undefined) => {
    setSelectedModelKey(modelKey);
    const key = `memorypal.selectedModel.${user.id}`;
    persistPreference(modelKey ? AsyncStorage.setItem(key, modelKey) : AsyncStorage.removeItem(key));
    persistPreference(api.selectModel(
      token, modelKey, persona === 'none' ? 'none' : 'default',
    ).then(() => undefined));
  };

  const updateDarkMode = (enabled: boolean) => {
    onDarkModeChange(enabled);
    persistPreference(AsyncStorage.setItem('memorypal.darkMode', String(enabled)));
  };

  const updateConversationMode = (mode: ConversationMode) => {
    setConversationMode(mode);
    persistPreference(AsyncStorage.setItem(`memorypal.conversationMode.${user.id}`, mode));
  };

  const updateCharacter = (id: CharacterId) => {
    setCharacterId(id);
    persistPreference(AsyncStorage.setItem(`memorypal.characterId.${user.id}`, id));
  };

  const activeThinkingMode = persona !== 'emotional_companion'
    && thinkingMode
    && modelCapabilities?.thinking_supported === true;
  const activeReasoningEffort = activeThinkingMode
    && modelCapabilities?.reasoning_efforts.includes(reasoningEffort)
    ? reasoningEffort
    : undefined;

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style={darkMode ? 'light' : 'dark'} />
      <View style={[styles.phone, tab === 'chat' && conversationMode === 'hybrid' && styles.hybridPhone]}>
        {accountOpen ? (
          <AccountScreen user={user} onClose={() => setAccountOpen(false)} />
        ) : (<>
        <View style={styles.screen}>
          {tab === 'home' && <HomeScreen token={token} user={user} casualMode={casualMode} persona={persona} voiceId={voiceId} voiceReplyEnabled={conversationMode === 'live' || voiceReplyEnabled} internetEnabled={internetEnabled} thinkingMode={activeThinkingMode} reasoningEffort={activeReasoningEffort} modelKey={persona !== 'emotional_companion' ? selectedModelKey : undefined} onModelKeyChange={updateSelectedModel} onPersonaChange={updatePersona} onVoiceIdChange={setVoiceId} onConversation={openVoiceConversation} onVoiceProcessingChange={updateVoiceProcessing} onOpenAccount={() => setAccountOpen(true)} onLogout={logout} />}
          <View
            pointerEvents={tab === 'chat' ? 'auto' : 'none'}
            style={[styles.chatScreen, tab !== 'chat' && styles.hiddenScreen]}
          >
            <ChatScreen
              token={token}
              isActive={tab === 'chat'}
              activeSessionId={sessionId}
              casualMode={casualMode}
              persona={persona}
              voiceId={voiceId}
              voiceReplyEnabled={voiceReplyEnabled}
              internetEnabled={internetEnabled}
              thinkingMode={activeThinkingMode}
              reasoningEffort={activeReasoningEffort}
              modelKey={persona !== 'emotional_companion' ? selectedModelKey : undefined}
              conversationMode={conversationMode}
              characterId={characterId}
              onConversationModeChange={updateConversationMode}
              onCharacterChange={updateCharacter}
              incomingMessage={incomingMessage}
              onIncomingMessageConsumed={consumeIncomingMessage}
              onSessionChange={updateConversation}
              onVoiceProcessingChange={updateVoiceProcessing}
            />
          </View>
          {tab === 'memory' && <MemoryScreen token={token} />}
          <View
            pointerEvents={tab === 'portrait' ? 'auto' : 'none'}
            style={[styles.portraitScreen, tab !== 'portrait' && styles.hiddenScreen]}
          >
            <PortraitScreen token={token} persona={persona} isActive={tab === 'portrait'} />
          </View>
          {tab === 'settings' && <SettingsScreen token={token} user={user} casualMode={casualMode} persona={persona} darkMode={darkMode} voiceReplyEnabled={voiceReplyEnabled} internetEnabled={internetEnabled} thinkingMode={thinkingMode} reasoningEffort={reasoningEffort} modelCapabilities={modelCapabilities} modelCapabilitiesLoading={modelCapabilitiesLoading} selectedModelKey={selectedModelKey} conversationMode={conversationMode} onCasualModeChange={updateCasualMode} onPersonaChange={updatePersona} onDarkModeChange={updateDarkMode} onVoiceReplyChange={updateVoiceReply} onInternetEnabledChange={updateInternetEnabled} onThinkingModeChange={updateThinkingMode} onReasoningEffortChange={updateReasoningEffort} onSelectedModelKeyChange={updateSelectedModel} onConversationModeChange={updateConversationMode} onOpenAccount={() => setAccountOpen(true)} logout={logout} />}
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
      {!!personaLoading && (
        <View style={styles.processingOverlay}>
          <BlurView intensity={32} style={StyleSheet.absoluteFill} tint={darkMode ? 'dark' : 'light'} />
          <View style={styles.processingShade} />
          <View style={styles.processingCard}>
            <ActivityIndicator color={colors.primary} size="large" />
            <Text style={styles.processingTitle}>페르소나 모델을 불러오고 있어요</Text>
            <Text style={styles.processingDescription}>
              {personaLoading === 'emotional_companion'
                ? '정서적 동반자 모델을 준비하는 중입니다.'
                : personaLoading === 'none'
                  ? '선택한 일반 대화 모델을 준비하는 중입니다.'
                  : '기본 대화 모델을 준비하는 중입니다.'}
            </Text>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

export default function App() {
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    void AsyncStorage.getItem('memorypal.darkMode').then((stored) => setDarkMode(stored === 'true')).catch(() => undefined);
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
  hybridPhone: { maxWidth: 1040 },
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
