import { useAudioPlayer } from 'expo-audio';
import * as DocumentPicker from 'expo-document-picker';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api } from '../api';
import { playWebAudio, unlockWebAudio } from '../audioPlayback';
import { MarkdownMessage } from '../components/MarkdownMessage';
import { useLiveRecorder } from '../hooks/useLiveRecorder';
import { useTheme, type ThemeColors } from '../theme';
import type { Attachment, Message, Persona, ReasoningEffort, Session } from '../types';

type Props = {
  token: string;
  isActive: boolean;
  activeSessionId?: string;
  casualMode: boolean;
  persona: Persona;
  voiceId?: string;
  voiceReplyEnabled: boolean;
  internetEnabled: boolean;
  thinkingMode: boolean;
  reasoningEffort?: ReasoningEffort;
  incomingMessage?: Message;
  onIncomingMessageConsumed: () => void;
  onSessionChange: (id: string) => void;
  onVoiceProcessingChange: (active: boolean, transcript?: string) => void;
};

function isAbortError(reason: unknown): boolean {
  return reason instanceof Error && reason.name === 'AbortError';
}

function messageFrom(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function mergeServerMessages(serverMessages: Message[], currentMessages: Message[]): Message[] {
  const currentById = new Map<string, Message>(
    currentMessages.map((message) => [message.id, message] as const),
  );
  const serverIds = new Set(serverMessages.map((message) => message.id));
  return [
    ...serverMessages.map((message) => currentById.get(message.id) ?? message),
    ...currentMessages.filter((message) => !serverIds.has(message.id)),
  ];
}

function upsertMessage(currentMessages: Message[], updatedMessage: Message): Message[] {
  const existingIndex = currentMessages.findIndex((message) => message.id === updatedMessage.id);
  if (existingIndex < 0) return [...currentMessages, updatedMessage];
  return currentMessages.map((message) => (
    message.id === updatedMessage.id ? updatedMessage : message
  ));
}

function AudioButton({ uri, onError, autoPlay = false }: { uri: string; onError: (message: string) => void; autoPlay?: boolean }) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const player = useAudioPlayer(uri);
  const autoPlayedUriRef = useRef<string | undefined>(undefined);
  const play = useCallback(async () => {
    try {
      if (Platform.OS === 'web') {
        await playWebAudio(uri);
        return;
      }
      await player.seekTo(0);
      player.play();
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : '음성을 재생하지 못했어요.');
    }
  }, [onError, player, uri]);

  useEffect(() => {
    if (!autoPlay || autoPlayedUriRef.current === uri) return;
    autoPlayedUriRef.current = uri;
    void play();
  }, [autoPlay, play, uri]);
  return (
    <Pressable onPress={() => void play()} style={styles.audioButton}>
      <Text style={styles.audioText}>▶ 음성으로 듣기</Text>
    </Pressable>
  );
}

export function ChatScreen({
  token,
  isActive,
  activeSessionId,
  casualMode,
  persona,
  voiceId,
  voiceReplyEnabled,
  internetEnabled,
  thinkingMode,
  reasoningEffort,
  incomingMessage,
  onIncomingMessageConsumed,
  onSessionChange,
  onVoiceProcessingChange,
}: Props) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const voiceRecorder = useLiveRecorder(token);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [error, setError] = useState('');
  const [deleteTargetId, setDeleteTargetId] = useState<string>();
  const [deletingSessionId, setDeletingSessionId] = useState<string>();
  const [voiceProcessing, setVoiceProcessing] = useState(false);
  const [autoPlayMessageId, setAutoPlayMessageId] = useState<string>();
  const [attachmentBusy, setAttachmentBusy] = useState(false);
  const [deletingAttachmentId, setDeletingAttachmentId] = useState<string>();
  const [regeneratingMessageId, setRegeneratingMessageId] = useState<string>();
  const [generatingAudioMessageId, setGeneratingAudioMessageId] = useState<string>();
  const generatingAudioMessageIdRef = useRef<string | undefined>(undefined);
  const scrollRef = useRef<ScrollView>(null);
  const activeSessionIdRef = useRef(activeSessionId);
  const isActiveRef = useRef(isActive);
  const selectionVersionRef = useRef(0);
  const sessionsRequestRef = useRef(0);
  const historyRequestRef = useRef(0);
  const attachmentsRequestRef = useRef(0);
  const contextMutationLockRef = useRef<symbol | undefined>(undefined);
  const preserveLocalStateForSessionRef = useRef<string | undefined>(undefined);
  const contextMutationBusy = busy
    || attachmentBusy
    || !!deletingAttachmentId
    || !!deletingSessionId
    || !!regeneratingMessageId
    || !!generatingAudioMessageId;

  const acquireContextMutation = (): symbol | undefined => {
    if (contextMutationLockRef.current) return undefined;
    const lock = Symbol('chat-context-mutation');
    contextMutationLockRef.current = lock;
    return lock;
  };

  const releaseContextMutation = (lock: symbol): void => {
    if (contextMutationLockRef.current === lock) contextMutationLockRef.current = undefined;
  };
  if (activeSessionIdRef.current !== activeSessionId) {
    activeSessionIdRef.current = activeSessionId;
    selectionVersionRef.current += 1;
  }
  isActiveRef.current = isActive;

  const changeSession = useCallback((id: string) => {
    selectionVersionRef.current += 1;
    activeSessionIdRef.current = id || undefined;
    onSessionChange(id);
  }, [onSessionChange]);

  useEffect(() => {
    if (isActive) return;
    setVoiceProcessing(false);
    setAutoPlayMessageId(undefined);
    onVoiceProcessingChange(false);
    void voiceRecorder.cancel();
  }, [isActive, onVoiceProcessingChange, voiceRecorder.cancel]);

  const loadSessions = useCallback(async ({ signal, selectFirst = false }: { signal?: AbortSignal; selectFirst?: boolean } = {}) => {
    const requestId = ++sessionsRequestRef.current;
    const selectionVersion = selectionVersionRef.current;
    let items: Session[];
    try {
      items = await api.sessions(token, signal);
    } catch (reason) {
      if (signal?.aborted || requestId !== sessionsRequestRef.current) return;
      throw reason;
    }
    if (signal?.aborted || requestId !== sessionsRequestRef.current) return;
    setSessions(items);
    if (selectFirst && selectionVersionRef.current === selectionVersion && !activeSessionIdRef.current && items[0]) {
      changeSession(items[0].id);
    }
  }, [changeSession, token]);

  useEffect(() => {
    const controller = new AbortController();
    void loadSessions({ signal: controller.signal, selectFirst: true }).catch((reason: unknown) => {
      if (!isAbortError(reason)) setError(messageFrom(reason, '대화 목록을 불러오지 못했어요.'));
    });
    return () => controller.abort();
  }, [loadSessions]);

  useEffect(() => {
    const controller = new AbortController();
    const requestedSessionId = activeSessionId;
    const historyRequestId = ++historyRequestRef.current;
    const attachmentsRequestId = ++attachmentsRequestRef.current;
    setError('');
    setAutoPlayMessageId(undefined);
    if (!requestedSessionId) {
      preserveLocalStateForSessionRef.current = undefined;
      setMessages([]);
      setAttachments([]);
      return () => controller.abort();
    }

    // Clear the previous session immediately and reject any result that is no longer current.
    const preserveLocalState = preserveLocalStateForSessionRef.current === requestedSessionId;
    preserveLocalStateForSessionRef.current = undefined;
    if (!preserveLocalState) {
      setMessages([]);
      setAttachments([]);
    }
    void api.history(token, requestedSessionId, controller.signal).then((items) => {
      if (
        !controller.signal.aborted
        && historyRequestRef.current === historyRequestId
        && activeSessionIdRef.current === requestedSessionId
      ) {
        setMessages((current) => mergeServerMessages(items, current));
      }
    }).catch((reason: unknown) => {
      if (
        !controller.signal.aborted
        && historyRequestRef.current === historyRequestId
        && activeSessionIdRef.current === requestedSessionId
        && !isAbortError(reason)
      ) {
        setError(messageFrom(reason, '대화 내용을 불러오지 못했어요.'));
      }
    });
    void api.attachments(token, requestedSessionId, controller.signal).then((items) => {
      if (
        !controller.signal.aborted
        && attachmentsRequestRef.current === attachmentsRequestId
        && activeSessionIdRef.current === requestedSessionId
      ) {
        setAttachments((current) => {
          const serverIds = new Set(items.map((attachment) => attachment.id));
          return [...items, ...current.filter((attachment) => !serverIds.has(attachment.id))];
        });
      }
    }).catch((reason: unknown) => {
      if (
        !controller.signal.aborted
        && attachmentsRequestRef.current === attachmentsRequestId
        && activeSessionIdRef.current === requestedSessionId
        && !isAbortError(reason)
      ) {
        setError(messageFrom(reason, '첨부파일 목록을 불러오지 못했어요.'));
      }
    });
    return () => controller.abort();
  }, [activeSessionId, token]);

  useEffect(() => {
    if (!incomingMessage) return;
    setMessages((current) => current.some((message) => message.id === incomingMessage.id)
      ? current
      : [...current, incomingMessage]);
    if (voiceReplyEnabled) {
      if (incomingMessage.audio_url) {
        if (isActiveRef.current) setAutoPlayMessageId(incomingMessage.id);
      } else setError('답변은 도착했지만 음성을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
    void loadSessions().catch(() => undefined);
    onIncomingMessageConsumed();
  }, [incomingMessage, loadSessions, onIncomingMessageConsumed, voiceReplyEnabled]);

  const send = async (valueOverride?: string, preserveInput = false) => {
    const value = (valueOverride ?? text).trim();
    const voiceSubmission = valueOverride !== undefined;
    if (
      !value
      || contextMutationBusy
      || contextMutationLockRef.current
      || (!voiceSubmission && (voiceRecorder.isRecording || voiceProcessing))
    ) return;
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    const requestedSessionId = activeSessionIdRef.current;
    const requestedSelectionVersion = selectionVersionRef.current;
    unlockWebAudio();
    const optimisticId = `pending-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const optimisticMessage: Message = {
      id: optimisticId,
      user_text: value,
      assistant_text: '',
      created_at: new Date().toISOString(),
    };
    if (!preserveInput) setText('');
    setBusy(true);
    setError('');
    setMessages((current) => [...current, optimisticMessage]);
    try {
      const response = await api.chatStream(
        token,
        value,
        (delta) => {
          if (
            activeSessionIdRef.current !== requestedSessionId
            || selectionVersionRef.current !== requestedSelectionVersion
          ) return;
          setMessages((current) => current.map((message) => (
            message.id === optimisticId
              ? { ...message, assistant_text: message.assistant_text + delta }
              : message
          )));
        },
        requestedSessionId, voiceId, voiceReplyEnabled, casualMode, persona, internetEnabled, thinkingMode,
        reasoningEffort,
      );
      const responseIsCurrent = activeSessionIdRef.current === requestedSessionId
        && selectionVersionRef.current === requestedSelectionVersion;
      if (responseIsCurrent) {
        if (response.session.id !== requestedSessionId) {
          preserveLocalStateForSessionRef.current = response.session.id;
          changeSession(response.session.id);
        }
        if (voiceReplyEnabled) {
          if (response.message.audio_url) {
            if (isActiveRef.current) setAutoPlayMessageId(response.message.id);
          } else setError('답변은 도착했지만 음성을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
        }
        setMessages((current) => [
          ...current.filter((message) => message.id !== optimisticId && message.id !== response.message.id),
          response.message,
        ]);
        setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
      } else if (requestedSessionId && activeSessionIdRef.current === requestedSessionId) {
        // The user left this session and returned while the request was pending. Re-read the
        // authoritative history instead of injecting a response from an older selection epoch.
        const reconciliationVersion = selectionVersionRef.current;
        const reconciliationRequestId = ++historyRequestRef.current;
        try {
          const items = await api.history(token, requestedSessionId);
          if (
            activeSessionIdRef.current === requestedSessionId
            && selectionVersionRef.current === reconciliationVersion
            && historyRequestRef.current === reconciliationRequestId
          ) {
            setMessages((current) => mergeServerMessages(items, current));
          }
        } catch (reason) {
          if (
            activeSessionIdRef.current === requestedSessionId
            && selectionVersionRef.current === reconciliationVersion
            && historyRequestRef.current === reconciliationRequestId
          ) {
            setError((current) => current || messageFrom(reason, '대화 내용을 새로 고치지 못했어요.'));
          }
        }
      }
      const refreshSelectionVersion = selectionVersionRef.current;
      void loadSessions().catch((reason: unknown) => {
        if (responseIsCurrent && selectionVersionRef.current === refreshSelectionVersion) {
          setError((current) => current || messageFrom(reason, '답변은 저장됐지만 대화 목록을 새로고침하지 못했어요.'));
        }
      });
    } catch (reason) {
      if (activeSessionIdRef.current === requestedSessionId && selectionVersionRef.current === requestedSelectionVersion) {
        setError(messageFrom(reason, '메시지를 보내지 못했어요.'));
        setMessages((current) => current.filter((message) => message.id !== optimisticId));
        if (!preserveInput) setText(value);
      }
    } finally {
      setBusy(false);
      releaseContextMutation(operationLock);
    }
  };

  const chooseSession = (id: string) => {
    if (id !== activeSessionIdRef.current) changeSession(id);
    setDrawer(false);
  };

  const regenerate = async (message: Message) => {
    if (
      contextMutationBusy
      || contextMutationLockRef.current
      || voiceRecorder.isRecording
      || voiceProcessing
      || message.id.startsWith('pending-')
    ) return;
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    const requestedSessionId = activeSessionIdRef.current;
    const requestedSelectionVersion = selectionVersionRef.current;
    unlockWebAudio();
    try {
      setRegeneratingMessageId(message.id);
      setError('');
      const response = await api.regenerate(
        token,
        message.id,
        voiceId,
        voiceReplyEnabled,
        casualMode,
        persona,
        internetEnabled,
        thinkingMode,
        reasoningEffort,
      );
      const responseIsCurrent = activeSessionIdRef.current === requestedSessionId
        && selectionVersionRef.current === requestedSelectionVersion;
      const returnedToMutatedSession = !!requestedSessionId
        && activeSessionIdRef.current === requestedSessionId
        && response.session.id === requestedSessionId;
      if (responseIsCurrent || returnedToMutatedSession) {
        // A completed server mutation is authoritative when the user has returned to that same session.
        setMessages((current) => upsertMessage(current, response.message));
        if (voiceReplyEnabled) {
          if (response.message.audio_url) {
            if (isActiveRef.current) setAutoPlayMessageId(response.message.id);
          } else setError('답변은 다시 생성했지만 음성을 만들지 못했어요.');
        }
      }
      void loadSessions().catch(() => undefined);
    } catch (reason) {
      if (
        (activeSessionIdRef.current === requestedSessionId
          && selectionVersionRef.current === requestedSelectionVersion)
        || (!!requestedSessionId && activeSessionIdRef.current === requestedSessionId)
      ) {
        setError(messageFrom(reason, '답변을 다시 생성하지 못했어요.'));
      }
    } finally {
      setRegeneratingMessageId(undefined);
      releaseContextMutation(operationLock);
    }
  };

  const generateMessageAudio = async (message: Message) => {
    if (
      contextMutationBusy
      || contextMutationLockRef.current
      || voiceRecorder.isRecording
      || voiceProcessing
      || generatingAudioMessageIdRef.current
      || message.id.startsWith('pending-')
    ) return;
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    const requestedSessionId = activeSessionIdRef.current;
    const requestedSelectionVersion = selectionVersionRef.current;
    generatingAudioMessageIdRef.current = message.id;
    unlockWebAudio();
    try {
      setGeneratingAudioMessageId(message.id);
      setError('');
      const updatedMessage = await api.messageAudio(token, message.id, voiceId);
      if (!updatedMessage.audio_url) throw new Error('음성을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.');
      const responseIsCurrent = activeSessionIdRef.current === requestedSessionId
        && selectionVersionRef.current === requestedSelectionVersion;
      const returnedToMutatedSession = !!requestedSessionId
        && activeSessionIdRef.current === requestedSessionId;
      if (responseIsCurrent || returnedToMutatedSession) {
        setMessages((current) => upsertMessage(current, updatedMessage));
        if (isActiveRef.current) setAutoPlayMessageId(updatedMessage.id);
      }
    } catch (reason) {
      if (
        (activeSessionIdRef.current === requestedSessionId
          && selectionVersionRef.current === requestedSelectionVersion)
        || (!!requestedSessionId && activeSessionIdRef.current === requestedSessionId)
      ) {
        setError(messageFrom(reason, '음성을 생성하지 못했어요.'));
      }
    } finally {
      generatingAudioMessageIdRef.current = undefined;
      setGeneratingAudioMessageId(undefined);
      releaseContextMutation(operationLock);
    }
  };

  const toggleVoiceInput = async () => {
    if (!isActiveRef.current) return;
    if (!voiceRecorder.isRecording && (contextMutationBusy || contextMutationLockRef.current)) return;
    if (voiceRecorder.isRecording) unlockWebAudio();
    try {
      setError('');
      if (!voiceRecorder.isRecording) {
        await voiceRecorder.start();
        return;
      }
      setVoiceProcessing(true);
      onVoiceProcessingChange(true);
      const transcript = await voiceRecorder.stop();
      if (!isActiveRef.current) return;
      if (!transcript) {
        setError('음성을 인식하지 못했어요. 조금 더 가까이에서 다시 말해 주세요.');
        return;
      }
      onVoiceProcessingChange(true, transcript);
      setVoiceProcessing(false);
      await send(transcript, true);
    } catch (reason) {
      if (isActiveRef.current && !isAbortError(reason)) {
        setError(reason instanceof Error ? reason.message : '음성 입력을 처리하지 못했어요.');
      }
    } finally {
      setVoiceProcessing(false);
      onVoiceProcessingChange(false);
    }
  };

  const pickAttachment = async () => {
    if (contextMutationBusy || contextMutationLockRef.current || voiceRecorder.isRecording || voiceProcessing) return;
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    const startingSessionId = activeSessionIdRef.current;
    const startingSelectionVersion = selectionVersionRef.current;
    let targetSessionId = startingSessionId;
    try {
      setAttachmentBusy(true);
      setError('');
      const result = await DocumentPicker.getDocumentAsync({
        type: [
          'text/plain',
          'text/markdown',
          'text/csv',
          'application/json',
          'application/pdf',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        ],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (result.canceled) return;
      if (activeSessionIdRef.current !== startingSessionId || selectionVersionRef.current !== startingSelectionVersion) return;
      let activateCreatedSession = false;
      if (!targetSessionId) {
        const session = await api.createSession(token, '첨부 문서 대화');
        targetSessionId = session.id;
        activateCreatedSession = true;
        if (activeSessionIdRef.current !== startingSessionId || selectionVersionRef.current !== startingSelectionVersion) {
          void loadSessions().catch(() => undefined);
          return;
        }
        setSessions((current) => [session, ...current.filter((item) => item.id !== session.id)]);
      }
      const asset = result.assets[0];
      if (!asset) throw new Error('선택한 파일 정보를 읽지 못했어요.');
      const uploaded = await api.uploadAttachment(
        token,
        targetSessionId,
        asset.uri,
        asset.name,
        asset.mimeType ?? 'application/octet-stream',
      );
      const sessionStillVisible = activateCreatedSession
        ? activeSessionIdRef.current === startingSessionId && selectionVersionRef.current === startingSelectionVersion
        : activeSessionIdRef.current === targetSessionId && selectionVersionRef.current === startingSelectionVersion;
      if (sessionStillVisible) {
        setAttachments((current) => [...current.filter((item) => item.id !== uploaded.id), uploaded]);
        if (activateCreatedSession) {
          preserveLocalStateForSessionRef.current = targetSessionId;
          changeSession(targetSessionId);
        }
      } else if (activeSessionIdRef.current === targetSessionId) {
        // Upload finished while this session was left and re-opened; reconcile the committed attachment.
        setAttachments((current) => [...current.filter((item) => item.id !== uploaded.id), uploaded]);
      }
    } catch (reason) {
      if (
        (activeSessionIdRef.current === startingSessionId
          && selectionVersionRef.current === startingSelectionVersion)
        || (!!targetSessionId && activeSessionIdRef.current === targetSessionId)
      ) {
        setError(messageFrom(reason, '파일을 첨부하지 못했어요.'));
      }
    } finally {
      setAttachmentBusy(false);
      releaseContextMutation(operationLock);
    }
  };

  const deleteAttachment = async (id: string) => {
    if (contextMutationBusy || contextMutationLockRef.current || voiceRecorder.isRecording || voiceProcessing) return;
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    const requestedSessionId = activeSessionIdRef.current;
    const requestedSelectionVersion = selectionVersionRef.current;
    try {
      setDeletingAttachmentId(id);
      setError('');
      await api.deleteAttachment(token, id);
      const responseIsCurrent = activeSessionIdRef.current === requestedSessionId
        && selectionVersionRef.current === requestedSelectionVersion;
      const returnedToMutatedSession = !!requestedSessionId
        && activeSessionIdRef.current === requestedSessionId;
      if (responseIsCurrent || returnedToMutatedSession) {
        attachmentsRequestRef.current += 1;
        setAttachments((current) => current.filter((item) => item.id !== id));
      }
    } catch (reason) {
      if (
        (activeSessionIdRef.current === requestedSessionId
          && selectionVersionRef.current === requestedSelectionVersion)
        || (!!requestedSessionId && activeSessionIdRef.current === requestedSessionId)
      ) {
        setError(messageFrom(reason, '첨부파일을 삭제하지 못했어요.'));
      }
    } finally {
      setDeletingAttachmentId(undefined);
      releaseContextMutation(operationLock);
    }
  };

  const requestSessionDelete = (id: string) => {
    if ((contextMutationBusy || contextMutationLockRef.current) && id === activeSessionIdRef.current) {
      setError('답변을 생성 중인 대화는 완료 후 삭제해 주세요.');
      return;
    }
    setDeleteTargetId(id);
  };

  const deleteSession = async (id: string) => {
    if (contextMutationBusy || contextMutationLockRef.current || voiceRecorder.isRecording || voiceProcessing) {
      setError('진행 중인 대화 작업이 끝난 뒤 삭제해 주세요.');
      return;
    }
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    setDeletingSessionId(id);
    setError('');
    try {
      await api.deleteSession(token, id);
      setSessions((current) => current.filter((session) => session.id !== id));
      setDeleteTargetId(undefined);
      if (id === activeSessionIdRef.current) {
        changeSession('');
        setMessages([]);
        setAttachments([]);
        setText('');
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '대화를 삭제하지 못했어요.');
    } finally {
      setDeletingSessionId(undefined);
      releaseContextMutation(operationLock);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={styles.root} keyboardVerticalOffset={90}>
      <View style={styles.header}>
        <Pressable accessibilityLabel="대화 목록" onPress={() => setDrawer(true)} style={styles.headerButton}><Text style={styles.headerIcon}>☰</Text></Pressable>
        <View style={styles.headerTitleWrap}>
          <Text numberOfLines={1} style={styles.headerTitle}>{sessions.find((item) => item.id === activeSessionId)?.title ?? 'MemoryPal Chat'}</Text>
          <Text style={styles.headerSub}>기억을 이어서 대화해요</Text>
        </View>
        <Pressable
          accessibilityLabel="새 대화"
          onPress={() => { setMessages([]); setAttachments([]); changeSession(''); }}
          style={styles.headerButton}
        ><Text style={styles.plus}>＋</Text></Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.messages}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
        ref={scrollRef}
      >
        {!messages.length && (
          <View style={styles.empty}>
            <Text style={styles.emptyMark}>M</Text>
            <Text style={styles.emptyTitle}>새 이야기를 시작해 볼까요?</Text>
            <Text style={styles.emptyText}>메인 화면에서 말하거나 아래에 메시지를 입력해 주세요.</Text>
          </View>
        )}
        {messages.map((message) => (
          <View key={message.id}>
            <View style={[styles.bubble, styles.userBubble]}><Text style={styles.userText}>{message.user_text}</Text></View>
            {!!(message.assistant_text.trim() || message.audio_url) && (
              <View style={[styles.bubble, styles.assistantBubble]}>
                {!!message.assistant_text.trim() && <MarkdownMessage>{message.assistant_text}</MarkdownMessage>}
                {!!message.audio_url
                  ? <AudioButton uri={message.audio_url} onError={setError} autoPlay={autoPlayMessageId === message.id} />
                  : !!message.assistant_text.trim() && !message.id.startsWith('pending-') && (
                    <Pressable
                      accessibilityLabel="답변 음성으로 듣기"
                      disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
                      onPress={() => void generateMessageAudio(message)}
                      style={[styles.audioButton, (contextMutationBusy || voiceRecorder.isRecording || voiceProcessing) && styles.sendDisabled]}
                    >
                      {generatingAudioMessageId === message.id
                        ? <View style={styles.audioLoading}><ActivityIndicator color={colors.primaryDark} size="small" /><Text style={styles.audioText}>음성 생성 중…</Text></View>
                        : <Text style={styles.audioText}>▶ 음성으로 듣기</Text>}
                    </Pressable>
                  )}
                {!!message.assistant_text.trim() && !message.id.startsWith('pending-') && (
                  <Pressable
                    accessibilityLabel="답변 다시 생성"
                    disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
                    onPress={() => void regenerate(message)}
                    style={[styles.regenerateButton, (contextMutationBusy || voiceRecorder.isRecording || voiceProcessing) && styles.sendDisabled]}
                  >
                    {regeneratingMessageId === message.id
                      ? <ActivityIndicator color={colors.primaryDark} size="small" />
                      : <Text style={styles.regenerateText}>↻ 다시 답변</Text>}
                  </Pressable>
                )}
              </View>
            )}
          </View>
        ))}
        {busy && !messages.some((message) => (
          message.id.startsWith('pending-') && message.assistant_text.trim()
        )) && (
          <View style={[styles.bubble, styles.assistantBubble]}>
            <ActivityIndicator color={colors.primary} />
          </View>
        )}
      </ScrollView>

      {!!error && <Text style={styles.error}>{error}</Text>}
      {(voiceRecorder.isRecording || voiceProcessing) && (
        <Text style={styles.recordingStatus}>
          {voiceProcessing
            ? '전체 녹음을 음성 인식하고 있어요…'
            : `음성 녹음 중 · ${Math.max(1, Math.round(voiceRecorder.durationMillis / 1000))}초 · 다시 누르면 인식해요`}
        </Text>
      )}
      {!!attachments.length && (
        <ScrollView
          contentContainerStyle={styles.attachmentList}
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.attachmentBar}
        >
          {attachments.map((attachment) => (
            <View key={attachment.id} style={styles.attachmentChip}>
              <Text numberOfLines={1} style={styles.attachmentName}>📄 {attachment.filename}</Text>
              <Text style={styles.attachmentSize}>{Math.max(1, Math.ceil(attachment.size_bytes / 1024))}KB</Text>
              <Pressable
                accessibilityLabel={`${attachment.filename} 첨부 삭제`}
                disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
                onPress={() => void deleteAttachment(attachment.id)}
                style={styles.attachmentDelete}
              >
                {deletingAttachmentId === attachment.id
                  ? <ActivityIndicator color={colors.primary} size="small" />
                  : <Text style={styles.attachmentDeleteText}>×</Text>}
              </Pressable>
            </View>
          ))}
        </ScrollView>
      )}
      <View style={styles.composer}>
        <TextInput
          maxLength={8000}
          multiline
          onChangeText={setText}
          onSubmitEditing={() => void send()}
          placeholder="메시지를 입력하세요…"
          placeholderTextColor="#A49DAB"
          style={styles.input}
          value={text}
        />
        <Pressable
          accessibilityLabel="RAG 문서 첨부"
          disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
          onPress={() => void pickAttachment()}
          style={[styles.attachButton, (contextMutationBusy || voiceRecorder.isRecording || voiceProcessing) && styles.sendDisabled]}
        >
          {attachmentBusy
            ? <ActivityIndicator color={colors.primary} size="small" />
            : <Text style={styles.attachButtonText}>＋</Text>}
        </Pressable>
        <Pressable
          accessibilityLabel={voiceRecorder.isRecording ? '음성 녹음 정지 및 인식' : '음성 입력 시작'}
          disabled={contextMutationBusy || voiceProcessing}
          onPress={() => void toggleVoiceInput()}
          style={[styles.micButton, voiceRecorder.isRecording && styles.micButtonActive, (contextMutationBusy || voiceProcessing) && styles.sendDisabled]}
        >
          {voiceProcessing
            ? <ActivityIndicator color={colors.primary} size="small" />
            : <Text style={[styles.micButtonText, voiceRecorder.isRecording && styles.micButtonTextActive]}>
                {voiceRecorder.isRecording ? '■' : '●'}
              </Text>}
        </Pressable>
        <Pressable disabled={!text.trim() || contextMutationBusy || voiceRecorder.isRecording || voiceProcessing} onPress={() => void send()} style={[styles.send, (!text.trim() || contextMutationBusy || voiceRecorder.isRecording || voiceProcessing) && styles.sendDisabled]}>
          <Text style={styles.sendText}>↑</Text>
        </Pressable>
      </View>

      <Modal animationType="slide" onRequestClose={() => setDrawer(false)} transparent visible={drawer}>
        <Pressable onPress={() => setDrawer(false)} style={styles.backdrop}>
          <Pressable onPress={() => undefined} style={styles.drawer}>
            <View style={styles.drawerHandle} />
            <Text style={styles.drawerTitle}>지난 대화</Text>
            <ScrollView>
              {sessions.map((session) => (
                <View key={session.id} style={[styles.sessionRow, session.id === activeSessionId && styles.sessionActive]}>
                  <Pressable onPress={() => chooseSession(session.id)} style={styles.sessionSelect}>
                    <Text numberOfLines={1} style={styles.sessionTitle}>{session.title}</Text>
                    <Text style={styles.sessionDate}>{new Date(session.updated_at).toLocaleDateString('ko-KR')}</Text>
                  </Pressable>
                  {deleteTargetId === session.id ? (
                    <View style={styles.deleteConfirm}>
                      <Pressable disabled={deletingSessionId === session.id} onPress={() => setDeleteTargetId(undefined)} style={styles.cancelDeleteButton}>
                        <Text style={styles.cancelDeleteText}>취소</Text>
                      </Pressable>
                      <Pressable disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing} onPress={() => void deleteSession(session.id)} style={styles.confirmDeleteButton}>
                        {deletingSessionId === session.id
                          ? <ActivityIndicator color="#FFFFFF" size="small" />
                          : <Text style={styles.confirmDeleteText}>삭제</Text>}
                      </Pressable>
                    </View>
                  ) : (
                    <Pressable accessibilityLabel={`${session.title} 삭제`} onPress={() => requestSessionDelete(session.id)} style={styles.deleteButton}>
                      <Text style={styles.deleteButtonText}>×</Text>
                    </Pressable>
                  )}
                </View>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </KeyboardAvoidingView>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  root: { flex: 1 },
  header: { minHeight: 68, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  headerButton: { width: 42, height: 42, alignItems: 'center', justifyContent: 'center' },
  headerIcon: { color: colors.ink, fontSize: 21 },
  plus: { color: colors.primaryDark, fontSize: 26 },
  headerTitleWrap: { flex: 1, alignItems: 'center' },
  headerTitle: { color: colors.ink, fontSize: 15, fontWeight: '800', maxWidth: 230 },
  headerSub: { color: colors.muted, fontSize: 10, marginTop: 2 },
  messages: { flexGrow: 1, padding: 18, paddingBottom: 25 },
  empty: { alignItems: 'center', marginTop: 80, paddingHorizontal: 30 },
  emptyMark: { width: 52, height: 52, textAlign: 'center', textAlignVertical: 'center', paddingTop: 10, borderRadius: 18, overflow: 'hidden', backgroundColor: colors.primarySoft, color: colors.primaryDark, fontSize: 22, fontWeight: '900' },
  emptyTitle: { color: colors.ink, fontSize: 18, fontWeight: '800', marginTop: 18 },
  emptyText: { color: colors.muted, fontSize: 13, textAlign: 'center', lineHeight: 20, marginTop: 7 },
  bubble: { maxWidth: '84%', borderRadius: 20, padding: 14, marginBottom: 12 },
  userBubble: { alignSelf: 'flex-end', backgroundColor: colors.primary, borderBottomRightRadius: 6 },
  assistantBubble: { alignSelf: 'flex-start', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 6 },
  userText: { color: '#FFFFFF', fontSize: 15, lineHeight: 22 },
  audioButton: { alignSelf: 'flex-start', marginTop: 11, backgroundColor: colors.primarySoft, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 999 },
  audioLoading: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  audioText: { color: colors.primaryDark, fontSize: 11, fontWeight: '800' },
  regenerateButton: { alignSelf: 'flex-start', minHeight: 30, marginTop: 8, paddingHorizontal: 10, borderRadius: 999, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.subtle },
  regenerateText: { color: colors.muted, fontSize: 11, fontWeight: '800' },
  error: { color: colors.danger, fontSize: 12, paddingHorizontal: 18, paddingVertical: 5 },
  recordingStatus: { color: colors.primaryDark, backgroundColor: colors.primarySoft, fontSize: 11, fontWeight: '700', paddingHorizontal: 18, paddingVertical: 8 },
  attachmentBar: { flexGrow: 0, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
  attachmentList: { gap: 8, paddingHorizontal: 12, paddingVertical: 9 },
  attachmentChip: { maxWidth: 260, height: 38, flexDirection: 'row', alignItems: 'center', gap: 6, paddingLeft: 10, paddingRight: 4, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.primarySoft },
  attachmentName: { maxWidth: 150, color: colors.ink, fontSize: 11, fontWeight: '700' },
  attachmentSize: { color: colors.muted, fontSize: 9 },
  attachmentDelete: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  attachmentDeleteText: { color: colors.muted, fontSize: 21, lineHeight: 23 },
  composer: { flexDirection: 'row', alignItems: 'center', gap: 9, padding: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
  input: { flex: 1, minHeight: 68, maxHeight: 110, backgroundColor: colors.input, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 22, textAlignVertical: 'center', color: colors.ink, fontSize: 15, lineHeight: 22 },
  send: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  attachButton: { width: 42, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.input },
  attachButtonText: { color: colors.primaryDark, fontSize: 24, fontWeight: '600' },
  micButton: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft },
  micButtonActive: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  micButtonText: { color: colors.primaryDark, fontSize: 18, fontWeight: '900' },
  micButtonTextActive: { color: colors.danger },
  sendDisabled: { opacity: 0.35 },
  sendText: { color: '#FFFFFF', fontSize: 23, fontWeight: '800' },
  backdrop: { flex: 1, backgroundColor: colors.overlay, justifyContent: 'flex-end' },
  drawer: { maxHeight: '72%', minHeight: 320, backgroundColor: colors.surface, borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 20 },
  drawerHandle: { width: 42, height: 4, borderRadius: 99, backgroundColor: colors.border, alignSelf: 'center', marginBottom: 20 },
  drawerTitle: { color: colors.ink, fontSize: 22, fontWeight: '900', marginBottom: 15 },
  sessionRow: { minHeight: 64, flexDirection: 'row', alignItems: 'center', borderRadius: 15, marginBottom: 5, paddingLeft: 15, paddingRight: 8 },
  sessionActive: { backgroundColor: colors.primarySoft },
  sessionSelect: { flex: 1, paddingVertical: 12 },
  sessionTitle: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  sessionDate: { color: colors.muted, fontSize: 11, marginTop: 4 },
  deleteButton: { width: 38, height: 38, borderRadius: 13, alignItems: 'center', justifyContent: 'center' },
  deleteButtonText: { color: colors.muted, fontSize: 24, lineHeight: 26 },
  deleteConfirm: { flexDirection: 'row', gap: 5, marginLeft: 7 },
  cancelDeleteButton: { height: 34, paddingHorizontal: 9, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.subtle },
  cancelDeleteText: { color: colors.muted, fontSize: 11, fontWeight: '800' },
  confirmDeleteButton: { minWidth: 48, height: 34, paddingHorizontal: 9, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.danger },
  confirmDeleteText: { color: '#FFFFFF', fontSize: 11, fontWeight: '900' },
});
