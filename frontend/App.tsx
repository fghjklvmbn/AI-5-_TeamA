import React, { useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { AuthProvider, useAuth } from './src/AuthContext';
import { BottomTabs, type Tab } from './src/components/BottomTabs';
import { ChatScreen } from './src/screens/ChatScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { LoginScreen } from './src/screens/LoginScreen';
import { MemoryScreen } from './src/screens/MemoryScreen';
import { SettingsScreen } from './src/screens/SettingsScreen';
import { colors } from './src/theme';

function MemoryPalApp() {
  const { loading, token, user, logout } = useAuth();
  const [tab, setTab] = useState<Tab>('home');
  const [sessionId, setSessionId] = useState<string>();

  if (loading) {
    return <View style={styles.loading}><ActivityIndicator color={colors.primary} size="large" /></View>;
  }
  if (!token || !user) return <LoginScreen />;

  const openConversation = (id: string) => {
    setSessionId(id || undefined);
    if (id) setTab('chat');
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <View style={styles.phone}>
        <View style={styles.screen}>
          {tab === 'home' && <HomeScreen token={token} user={user} sessionId={sessionId} onConversation={openConversation} />}
          {tab === 'chat' && <ChatScreen token={token} activeSessionId={sessionId} onSessionChange={openConversation} />}
          {tab === 'memory' && <MemoryScreen token={token} />}
          {tab === 'settings' && <SettingsScreen token={token} user={user} logout={logout} />}
        </View>
        <BottomTabs current={tab} onChange={setTab} />
      </View>
    </SafeAreaView>
  );
}

export default function App() {
  return <SafeAreaProvider><AuthProvider><MemoryPalApp /></AuthProvider></SafeAreaProvider>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F0ECF4', alignItems: 'center' },
  phone: { flex: 1, width: '100%', maxWidth: 560, backgroundColor: colors.background },
  screen: { flex: 1 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background },
});
