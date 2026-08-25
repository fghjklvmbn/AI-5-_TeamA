import * as DocumentPicker from 'expo-document-picker';
import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
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
  useWindowDimensions,
  View,
} from 'react-native';

import { api, createAIPipelineTrace, type AIPipelineTrace } from '../api';
import { unlockWebAudio } from '../audioPlayback';
import { MarkdownMessage } from '../components/MarkdownMessage';
import { ConversationContextControls } from '../components/ConversationContextControls';
import { ConversationModeTabs } from '../components/ConversationModeTabs';
import { MessageAudioButton } from '../components/MessageAudioButton';
import { characterCueForPlayback, useCharacterAudioState } from '../hooks/useCharacterAudioState';
import { useLiveRecorder } from '../hooks/useLiveRecorder';
import { useTheme, type ThemeColors } from '../theme';
import type { Attachment, CharacterActivity, CharacterId, ConversationMode, Message, Persona, ReasoningEffort, Session } from '../types';
import { recentVoiceRefreshMessages, splitSearchSources } from '../utils/messageContent';

const CharacterStage = React.lazy(() => import('../components/CharacterStage'));

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
  modelKey?: string;
  conversationMode: ConversationMode;
  characterId: CharacterId;
  incomingMessage?: Message;
  onIncomingMessageConsumed: () => void;
  onSessionChange: (id: string) => void;
  onVoiceProcessingChange: (active: boolean, transcript?: string) => void;
  onConversationModeChange: (mode: ConversationMode) => void;
  onCharacterChange: (characterId: CharacterId) => void;
  onPersonaChange: (persona: Persona) => void | Promise<void>;
  onModelKeyChange: (modelKey: string | undefined) => void | Promise<void>;
  onVoiceIdChange: (voiceId: string | undefined) => void;
};

type VoiceRefreshProgress = {
  completed: number;
  total: number;
  failed: number;
  messageId: string;
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
  modelKey,
  conversationMode,
  characterId,
  incomingMessage,
  onIncomingMessageConsumed,
  onSessionChange,
  onVoiceProcessingChange,
  onConversationModeChange,
  onCharacterChange,
  onPersonaChange,
  onModelKeyChange,
  onVoiceIdChange,
}: Props) {
  const { colors } = useTheme();
  const { width: viewportWidth, height: viewportHeight } = useWindowDimensions();
  const compact = viewportWidth <= 480;
  const shortViewport = compact && viewportHeight <= 650;
  const compactCharacter = compact && (
    conversationMode === 'hybrid'
    || (conversationMode === 'live' && viewportHeight <= 780)
  );
  const styles = createStyles(colors, compact);
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
  const [voiceRefreshProgress, setVoiceRefreshProgress] = useState<VoiceRefreshProgress>();
  const [expandedSourceMessageIds, setExpandedSourceMessageIds] = useState<Set<string>>(
    () => new Set(),
  );
  const characterAudio = useCharacterAudioState();
  const generatingAudioMessageIdRef = useRef<string | undefined>(undefined);
  const inputRef = useRef<TextInput>(null);
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
    || !!voiceRefreshProgress;
  const shouldSpeak = conversationMode === 'live' || voiceReplyEnabled;
  const characterActivity: CharacterActivity = voiceRecorder.isRecording
    ? 'listening'
    : voiceProcessing || busy
      ? 'thinking'
      : characterAudio.playing
        ? 'speaking'
        : 'idle';
  const characterCue = characterCueForPlayback(messages, characterAudio.messageId);
  const autoPlayMessage = autoPlayMessageId
    ? messages.find((message) => message.id === autoPlayMessageId && !!message.audio_url)
    : undefined;

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
    if (shouldSpeak) {
      if (incomingMessage.audio_url) {
        if (isActiveRef.current) setAutoPlayMessageId(incomingMessage.id);
      } else setError('답변은 도착했지만 음성을 만들지 못했어요. 잠시 후 다시 시도해 주세요.');
    }
    void loadSessions().catch(() => undefined);
    onIncomingMessageConsumed();
  }, [incomingMessage, loadSessions, onIncomingMessageConsumed, shouldSpeak]);

  const send = async (
    valueOverride?: string,
    preserveInput = false,
    suppliedTrace?: AIPipelineTrace,
  ) => {
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
    const requestAttachments = [...attachments];
    const requestAttachmentIds = new Set(attachments.map((attachment) => attachment.id));
    const pipelineTrace = suppliedTrace ?? createAIPipelineTrace([
      'llm', ...(shouldSpeak ? ['tts' as const] : []),
    ]);
    unlockWebAudio();
    const optimisticId = `pending-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const optimisticMessage: Message = {
      id: optimisticId,
      user_text: value,
      assistant_text: '',
      created_at: new Date().toISOString(),
      attachments: requestAttachments,
    };
    if (!preserveInput) {
      setText('');
      // react-native-web can retain its native textarea value after an Enter
      // submit even though the controlled state is already empty. Clear both
      // layers so the sent text cannot be submitted again accidentally.
      inputRef.current?.clear();
    }
    if (requestAttachmentIds.size) {
      attachmentsRequestRef.current += 1;
      setAttachments((current) => current.filter(
        (attachment) => !requestAttachmentIds.has(attachment.id),
      ));
    }
    setBusy(true);
    setError('');
    setMessages((current) => [...current, optimisticMessage]);
    let bufferedDelta = '';
    let deltaTimer: ReturnType<typeof setTimeout> | undefined;
    let audioMessage: Message | undefined;
    let audioSessionId = requestedSessionId;
    const flushDelta = () => {
      if (!bufferedDelta) return;
      const delta = bufferedDelta;
      bufferedDelta = '';
      setMessages((current) => current.map((message) => (
        message.id === optimisticId
          ? { ...message, assistant_text: message.assistant_text + delta }
          : message
      )));
    };
    try {
      const response = await api.chatStream(
        token,
        value,
        (delta) => {
          if (
            activeSessionIdRef.current !== requestedSessionId
            || selectionVersionRef.current !== requestedSelectionVersion
          ) return;
          bufferedDelta += delta;
          if (!deltaTimer) {
            deltaTimer = setTimeout(() => {
              deltaTimer = undefined;
              flushDelta();
            }, 50);
          }
        },
        requestedSessionId, voiceId, false, casualMode, persona, internetEnabled, thinkingMode,
        reasoningEffort,
        modelKey,
        pipelineTrace,
      );
      if (deltaTimer) clearTimeout(deltaTimer);
      deltaTimer = undefined;
      flushDelta();
      const responseIsCurrent = activeSessionIdRef.current === requestedSessionId
        && selectionVersionRef.current === requestedSelectionVersion;
      if (responseIsCurrent) {
        attachmentsRequestRef.current += 1;
        setAttachments((current) => current.filter(
          (attachment) => !requestAttachmentIds.has(attachment.id),
        ));
        if (response.session.id !== requestedSessionId) {
          preserveLocalStateForSessionRef.current = response.session.id;
          changeSession(response.session.id);
        }
        if (shouldSpeak) {
          audioMessage = response.message;
          audioSessionId = response.session.id;
        }
        setMessages((current) => [
          ...current.filter((message) => message.id !== optimisticId && message.id !== response.message.id),
          response.message.attachments?.length
            ? response.message
            : { ...response.message, attachments: requestAttachments },
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
        setAttachments((current) => {
          const currentIds = new Set(current.map((attachment) => attachment.id));
          return [...requestAttachments.filter((attachment) => !currentIds.has(attachment.id)), ...current];
        });
        if (!preserveInput) setText(value);
      }
    } finally {
      if (deltaTimer) clearTimeout(deltaTimer);
      setBusy(false);
      releaseContextMutation(operationLock);
      if (audioMessage) {
        const target = audioMessage;
        generatingAudioMessageIdRef.current = target.id;
        setGeneratingAudioMessageId(target.id);
        void api.messageAudio(token, target.id, voiceId, pipelineTrace).then((updated) => {
          if (activeSessionIdRef.current !== audioSessionId || !updated.audio_url) return;
          setMessages((current) => upsertMessage(current, updated));
          if (isActiveRef.current) setAutoPlayMessageId(updated.id);
        }).catch((reason) => {
          if (activeSessionIdRef.current === audioSessionId) {
            setError(messageFrom(reason, '답변은 도착했지만 음성을 만들지 못했어요.'));
          }
        }).finally(() => {
          generatingAudioMessageIdRef.current = undefined;
          setGeneratingAudioMessageId(undefined);
        });
      }
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
    const requestAttachmentIds = new Set(attachments.map((attachment) => attachment.id));
    unlockWebAudio();
    try {
      setRegeneratingMessageId(message.id);
      setError('');
      const response = await api.regenerate(
        token,
        message.id,
        voiceId,
        shouldSpeak,
        casualMode,
        persona,
        internetEnabled,
        thinkingMode,
        reasoningEffort,
        modelKey,
      );
      const responseIsCurrent = activeSessionIdRef.current === requestedSessionId
        && selectionVersionRef.current === requestedSelectionVersion;
      const returnedToMutatedSession = !!requestedSessionId
        && activeSessionIdRef.current === requestedSessionId
        && response.session.id === requestedSessionId;
      if (responseIsCurrent || returnedToMutatedSession) {
        // A completed server mutation is authoritative when the user has returned to that same session.
        attachmentsRequestRef.current += 1;
        setAttachments((current) => current.filter(
          (attachment) => !requestAttachmentIds.has(attachment.id),
        ));
        setMessages((current) => upsertMessage(current, response.message));
        if (shouldSpeak) {
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

  const changeResponseVoice = async (nextVoiceId: string | undefined) => {
    if (nextVoiceId === voiceId) return;
    onVoiceIdChange(nextVoiceId);
    const targets = recentVoiceRefreshMessages(messages);
    if (!targets.length) return;
    const operationLock = acquireContextMutation();
    if (!operationLock) return;
    const requestedSessionId = activeSessionIdRef.current;
    let failed = 0;
    setAutoPlayMessageId(undefined);
    try {
      for (let index = 0; index < targets.length; index += 1) {
        const message = targets[index]!;
        generatingAudioMessageIdRef.current = message.id;
        setGeneratingAudioMessageId(message.id);
        setVoiceRefreshProgress({
          completed: index, total: targets.length, failed, messageId: message.id,
        });
        try {
          const updated = await api.messageAudio(
            token, message.id, nextVoiceId, undefined, true,
          );
          if (!updated.audio_url) throw new Error('새 응답 음성을 생성하지 못했어요.');
          if (activeSessionIdRef.current === requestedSessionId) {
            setMessages((current) => upsertMessage(current, updated));
          }
        } catch {
          failed += 1;
        }
        setVoiceRefreshProgress({
          completed: index + 1, total: targets.length, failed, messageId: message.id,
        });
      }
      if (failed) {
        setError(`최근 ${targets.length}개 답변 중 ${failed}개의 음성을 변경하지 못했어요.`);
      } else {
        setError('');
      }
    } finally {
      generatingAudioMessageIdRef.current = undefined;
      setGeneratingAudioMessageId(undefined);
      setVoiceRefreshProgress(undefined);
      releaseContextMutation(operationLock);
    }
  };

  const toggleVoiceInput = async () => {
    if (!isActiveRef.current) return;
    if (!voiceRecorder.isRecording && (contextMutationBusy || contextMutationLockRef.current)) return;
    // Real-time mode has no visible audio control. Unlock the shared browser
    // player on the user's first microphone tap so the later TTS response can
    // start without being rejected by autoplay policy.
    if (conversationMode === 'live' || voiceRecorder.isRecording) unlockWebAudio();
    try {
      setError('');
      if (!voiceRecorder.isRecording) {
        await voiceRecorder.start();
        return;
      }
      setVoiceProcessing(true);
      if (conversationMode !== 'live') onVoiceProcessingChange(true);
      const pipelineTrace = createAIPipelineTrace([
        'stt', 'llm', ...(shouldSpeak ? ['tts' as const] : []),
      ]);
      const transcript = await voiceRecorder.stop(pipelineTrace);
      if (!isActiveRef.current) return;
      if (!transcript) {
        setError('음성을 인식하지 못했어요. 조금 더 가까이에서 다시 말해 주세요.');
        return;
      }
      if (conversationMode !== 'live') onVoiceProcessingChange(true, transcript);
      setVoiceProcessing(false);
      await send(transcript, true, pipelineTrace);
    } catch (reason) {
      if (isActiveRef.current && !isAbortError(reason)) {
        setError(reason instanceof Error ? reason.message : '음성 입력을 처리하지 못했어요.');
      }
    } finally {
      setVoiceProcessing(false);
      if (conversationMode !== 'live') onVoiceProcessingChange(false);
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

      <ConversationModeTabs compact={compact} value={conversationMode} onChange={onConversationModeChange} />
      <ConversationContextControls
        compact={compact}
        disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
        modelKey={modelKey}
        onModelKeyChange={onModelKeyChange}
        onPersonaChange={onPersonaChange}
        onVoiceIdChange={(nextVoiceId) => { void changeResponseVoice(nextVoiceId); }}
        persona={persona}
        token={token}
        voiceId={voiceId}
      />
      {!!voiceRefreshProgress && (
        <View accessibilityLiveRegion="polite" style={styles.voiceRefreshStatus}>
          <ActivityIndicator color={colors.primary} size="small" />
          <View style={styles.voiceRefreshTextWrap}>
            <Text style={styles.voiceRefreshTitle}>응답 음성을 변경하고 있어요</Text>
            <Text style={styles.voiceRefreshDetail}>
              최신 답변부터 순차 처리 중 · {Math.min(voiceRefreshProgress.completed + 1, voiceRefreshProgress.total)} / {voiceRefreshProgress.total}
            </Text>
          </View>
        </View>
      )}

      <View style={[
        styles.conversationArea,
        conversationMode === 'hybrid' && styles.hybridArea,
        conversationMode === 'hybrid' && compact && styles.hybridAreaCompact,
      ]}>
      {conversationMode !== 'chat' && <Suspense fallback={<View style={styles.characterLoading}><ActivityIndicator color={colors.primary} /><Text style={styles.characterLoadingText}>캐릭터 영역을 준비하고 있어요…</Text></View>}>
        <CharacterStage compact={compactCharacter} dense={shortViewport && conversationMode === 'hybrid'} fill={conversationMode === 'live'} characterId={characterId} activity={characterActivity} cue={characterCue} onCharacterChange={onCharacterChange} />
      </Suspense>}
      {conversationMode !== 'live' && <ScrollView
        style={styles.messagePane}
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
        {messages.map((message) => {
          const displayContent = splitSearchSources(message.assistant_text);
          const sourcesExpanded = expandedSourceMessageIds.has(message.id);
          return (
          <View key={message.id}>
            <View style={[styles.bubble, styles.userBubble]}>
              {!!message.attachments?.length && (
                <View style={styles.messageAttachmentLine}>
                  {message.attachments.map((attachment) => (
                    <Pressable
                      accessibilityLabel={`${attachment.filename} 파일 열기`}
                      accessibilityRole="link"
                      key={attachment.id}
                      onPress={() => void api.openAttachment(token, attachment).catch((reason) => {
                        setError(messageFrom(reason, '첨부파일을 열지 못했어요.'));
                      })}
                      style={styles.messageAttachmentLink}
                    >
                      <Text numberOfLines={1} style={styles.messageAttachmentText}>📄 {attachment.filename}</Text>
                    </Pressable>
                  ))}
                </View>
              )}
              <Text style={styles.userText}>{message.user_text}</Text>
            </View>
            {!!(message.assistant_text.trim() || message.audio_url) && (
              <View style={[styles.bubble, styles.assistantBubble]}>
                {!!displayContent.body.trim() && (
                  <MarkdownMessage streaming={message.id.startsWith('pending-')}>
                    {displayContent.body}
                  </MarkdownMessage>
                )}
                {!!displayContent.sources && (
                  <View style={styles.sourcePanel}>
                    <Pressable
                      accessibilityLabel={`검색 출처 ${sourcesExpanded ? '접기' : '펼치기'}`}
                      accessibilityState={{ expanded: sourcesExpanded }}
                      onPress={() => setExpandedSourceMessageIds((current) => {
                        const next = new Set(current);
                        if (next.has(message.id)) next.delete(message.id);
                        else next.add(message.id);
                        return next;
                      })}
                      style={styles.sourceHeader}
                    >
                      <Text style={styles.sourceTitle}>
                        검색 출처{displayContent.sourceCount ? ` ${displayContent.sourceCount}개` : ''}
                      </Text>
                      <Text style={styles.sourceAction}>{sourcesExpanded ? '닫기' : '보기'}</Text>
                    </Pressable>
                    {sourcesExpanded && (
                      <View style={styles.sourceBody}>
                        <MarkdownMessage>{displayContent.sources}</MarkdownMessage>
                      </View>
                    )}
                  </View>
                )}
                {!!message.audio_url
                  ? <MessageAudioButton uri={message.audio_url} messageId={message.id} onError={setError} />
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
          );
        })}
        {busy && !messages.some((message) => (
          message.id.startsWith('pending-') && message.assistant_text.trim()
        )) && (
          <View style={[styles.bubble, styles.assistantBubble]}>
            <ActivityIndicator color={colors.primary} />
          </View>
        )}
      </ScrollView>}
      </View>

      {!!autoPlayMessage?.audio_url && (
        <MessageAudioButton
          autoPlay
          controls={false}
          messageId={autoPlayMessage.id}
          onError={setError}
          uri={autoPlayMessage.audio_url}
        />
      )}

      {!!error && <Text style={styles.error}>{error}</Text>}
      {(voiceRecorder.isRecording || voiceProcessing) && (
        <Text style={styles.recordingStatus}>
          {voiceProcessing
            ? '전체 녹음을 음성 인식하고 있어요…'
            : `음성 녹음 중 · ${Math.max(1, Math.round(voiceRecorder.durationMillis / 1000))}초 · 다시 누르면 인식해요`}
        </Text>
      )}
      {conversationMode !== 'live' && !!attachments.length && (
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
      {conversationMode === 'live' ? <View style={styles.liveComposer}>
        <Text style={styles.liveGuide}>{voiceRecorder.isRecording ? '말씀을 마치면 버튼을 다시 눌러주세요' : '버튼을 누르고 캐릭터에게 말해보세요'}</Text>
        <Pressable
          accessibilityLabel={voiceRecorder.isRecording ? '실시간 음성 입력 정지' : '실시간 음성 입력 시작'}
          disabled={contextMutationBusy || voiceProcessing}
          onPress={() => void toggleVoiceInput()}
          style={[styles.liveMic, voiceRecorder.isRecording && styles.liveMicActive, (contextMutationBusy || voiceProcessing) && styles.sendDisabled]}
        >
          {voiceProcessing
            ? <ActivityIndicator color="#FFFFFF" size="large" />
            : <Text style={styles.liveMicText}>{voiceRecorder.isRecording ? '■' : '●'}</Text>}
        </Pressable>
      </View> : <View style={[styles.composer, compact && styles.composerCompact, shortViewport && styles.composerShort]}>
        <TextInput
          ref={inputRef}
          maxLength={8000}
          multiline
          onChangeText={setText}
          onKeyPress={(event) => {
            if (Platform.OS === 'web' && event.nativeEvent.key === 'Enter') void send();
          }}
          onSubmitEditing={() => void send()}
          placeholder="메시지를 입력하세요…"
          placeholderTextColor="#A49DAB"
          returnKeyType="send"
          style={[styles.input, compact && styles.inputCompact, shortViewport && styles.inputShort]}
          submitBehavior="submit"
          value={text}
        />
        <View style={[styles.composerActions, compact && styles.composerActionsCompact, shortViewport && styles.composerActionsShort]}>
          <Pressable
            accessibilityLabel="RAG 문서 첨부"
            disabled={contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
            onPress={() => void pickAttachment()}
            style={[styles.attachButton, compact && styles.compactActionButton, shortViewport && styles.shortActionButton, (contextMutationBusy || voiceRecorder.isRecording || voiceProcessing) && styles.sendDisabled]}
          >
            {attachmentBusy
              ? <ActivityIndicator color={colors.primary} size="small" />
              : <Text style={styles.attachButtonText}>＋</Text>}
          </Pressable>
          <Pressable
            accessibilityLabel={voiceRecorder.isRecording ? '음성 녹음 정지 및 인식' : '음성 입력 시작'}
            disabled={contextMutationBusy || voiceProcessing}
            onPress={() => void toggleVoiceInput()}
            style={[styles.micButton, compact && styles.compactActionButton, shortViewport && styles.shortActionButton, voiceRecorder.isRecording && styles.micButtonActive, (contextMutationBusy || voiceProcessing) && styles.sendDisabled]}
          >
            {voiceProcessing
              ? <ActivityIndicator color={colors.primary} size="small" />
              : <Text style={[styles.micButtonText, voiceRecorder.isRecording && styles.micButtonTextActive]}>
                  {voiceRecorder.isRecording ? '■' : '●'}
                </Text>}
          </Pressable>
          <Pressable
            accessibilityLabel="메시지 전송"
            disabled={!text.trim() || contextMutationBusy || voiceRecorder.isRecording || voiceProcessing}
            onPress={() => void send()}
            style={[styles.send, compact && styles.sendCompact, shortViewport && styles.sendShort, (!text.trim() || contextMutationBusy || voiceRecorder.isRecording || voiceProcessing) && styles.sendDisabled]}
          >
            <Text style={styles.sendText}>↑</Text>
          </Pressable>
        </View>
      </View>}

      <Modal animationType="fade" onRequestClose={() => setDrawer(false)} transparent visible={drawer}>
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

const createStyles = (colors: ThemeColors, compact: boolean) => StyleSheet.create({
  root: { flex: 1 },
  header: { minHeight: compact ? 56 : 68, flexDirection: 'row', alignItems: 'center', paddingHorizontal: compact ? 8 : 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  headerButton: { width: compact ? 38 : 42, height: compact ? 38 : 42, alignItems: 'center', justifyContent: 'center' },
  headerIcon: { color: colors.ink, fontSize: 21 },
  plus: { color: colors.primaryDark, fontSize: 26 },
  headerTitleWrap: { flex: 1, alignItems: 'center' },
  headerTitle: { color: colors.ink, fontSize: compact ? 14 : 15, fontWeight: '800', maxWidth: compact ? 190 : 230 },
  headerSub: { color: colors.muted, fontSize: compact ? 9 : 10, marginTop: 2 },
  voiceRefreshStatus: { minHeight: 52, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: compact ? 12 : 16, paddingVertical: 9, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, backgroundColor: colors.primarySoft },
  voiceRefreshTextWrap: { flex: 1, minWidth: 0 },
  voiceRefreshTitle: { color: colors.primaryDark, fontSize: 11, fontWeight: '900' },
  voiceRefreshDetail: { color: colors.muted, fontSize: 9, marginTop: 3 },
  conversationArea: { flex: 1, minHeight: 0 },
  hybridArea: { flexDirection: 'row' },
  hybridAreaCompact: { flexDirection: 'column' },
  messagePane: { flex: 1, minWidth: 0 },
  characterLoading: { flex: 1, minHeight: 280, alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: colors.subtle },
  characterLoadingText: { color: colors.muted, fontSize: 11 },
  messages: { flexGrow: 1, padding: compact ? 12 : 18, paddingBottom: compact ? 18 : 25 },
  empty: { alignItems: 'center', marginTop: compact ? 44 : 80, paddingHorizontal: compact ? 18 : 30 },
  emptyMark: { width: 52, height: 52, textAlign: 'center', textAlignVertical: 'center', paddingTop: 10, borderRadius: 18, overflow: 'hidden', backgroundColor: colors.primarySoft, color: colors.primaryDark, fontSize: 22, fontWeight: '900' },
  emptyTitle: { color: colors.ink, fontSize: compact ? 16 : 18, fontWeight: '800', marginTop: compact ? 14 : 18 },
  emptyText: { color: colors.muted, fontSize: 13, textAlign: 'center', lineHeight: 20, marginTop: 7 },
  bubble: { maxWidth: compact ? '92%' : '84%', borderRadius: compact ? 17 : 20, padding: compact ? 12 : 14, marginBottom: compact ? 10 : 12 },
  userBubble: { alignSelf: 'flex-end', backgroundColor: colors.primary, borderBottomRightRadius: 6 },
  messageAttachmentLine: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8, paddingBottom: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(255,255,255,.35)' },
  messageAttachmentLink: { maxWidth: compact ? 220 : 250, borderRadius: 7, backgroundColor: 'rgba(255,255,255,.16)', paddingHorizontal: 8, paddingVertical: 5 },
  messageAttachmentText: { color: '#FFFFFF', fontSize: 11, fontWeight: '800', textDecorationLine: 'underline' },
  assistantBubble: { alignSelf: 'flex-start', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 6 },
  userText: { color: '#FFFFFF', fontSize: 15, lineHeight: 22 },
  sourcePanel: { marginTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  sourceHeader: { minHeight: 42, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  sourceTitle: { color: colors.muted, fontSize: 12, fontWeight: '800' },
  sourceAction: { color: colors.primaryDark, fontSize: 11, fontWeight: '800' },
  sourceBody: { paddingTop: 2, paddingBottom: 4 },
  audioButton: { alignSelf: 'flex-start', marginTop: 11, backgroundColor: colors.primarySoft, paddingHorizontal: 11, paddingVertical: 7, borderRadius: 999 },
  audioLoading: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  audioText: { color: colors.primaryDark, fontSize: 11, fontWeight: '800' },
  regenerateButton: { alignSelf: 'flex-start', minHeight: 30, marginTop: 8, paddingHorizontal: 10, borderRadius: 999, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.subtle },
  regenerateText: { color: colors.muted, fontSize: 11, fontWeight: '800' },
  error: { color: colors.danger, fontSize: 12, paddingHorizontal: compact ? 12 : 18, paddingVertical: 5 },
  recordingStatus: { color: colors.primaryDark, backgroundColor: colors.primarySoft, fontSize: 11, fontWeight: '700', paddingHorizontal: compact ? 12 : 18, paddingVertical: 8 },
  attachmentBar: { flexGrow: 0, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
  attachmentList: { gap: 8, paddingHorizontal: 12, paddingVertical: 9 },
  attachmentChip: { maxWidth: 260, height: 38, flexDirection: 'row', alignItems: 'center', gap: 6, paddingLeft: 10, paddingRight: 4, borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.primarySoft },
  attachmentName: { maxWidth: 150, color: colors.ink, fontSize: 11, fontWeight: '700' },
  attachmentSize: { color: colors.muted, fontSize: 9 },
  attachmentDelete: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  attachmentDeleteText: { color: colors.muted, fontSize: 21, lineHeight: 23 },
  composer: { flexDirection: 'row', alignItems: 'center', gap: 9, padding: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
  composerCompact: { flexDirection: 'column', alignItems: 'stretch', gap: 8, paddingHorizontal: 10, paddingTop: 9, paddingBottom: 8 },
  composerShort: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 8, paddingVertical: 7 },
  composerActions: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  composerActionsCompact: { width: '100%' },
  composerActionsShort: { width: 'auto', gap: 6 },
  liveComposer: { minHeight: 128, alignItems: 'center', justifyContent: 'center', gap: 10, padding: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border, backgroundColor: colors.surface },
  liveGuide: { color: colors.muted, fontSize: 10, fontWeight: '700' },
  liveMic: { width: 72, height: 72, borderRadius: 36, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, borderWidth: 5, borderColor: colors.primarySoft },
  liveMicActive: { backgroundColor: colors.danger, borderColor: colors.dangerSoft },
  liveMicText: { color: '#FFFFFF', fontSize: 25, fontWeight: '900' },
  input: { flex: 1, minHeight: 68, maxHeight: 110, backgroundColor: colors.input, borderRadius: 20, paddingHorizontal: 16, paddingVertical: 22, textAlignVertical: 'center', color: colors.ink, fontSize: 15, lineHeight: 22 },
  inputCompact: { width: '100%', flex: 0, minHeight: 48, maxHeight: 92, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, lineHeight: 20 },
  inputShort: { width: 'auto', flex: 1, minHeight: 44, maxHeight: 72, paddingHorizontal: 11, paddingVertical: 10, fontSize: 13, lineHeight: 18 },
  send: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  attachButton: { width: 42, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.border, backgroundColor: colors.input },
  attachButtonText: { color: colors.primaryDark, fontSize: 24, fontWeight: '600' },
  micButton: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.primarySoft },
  micButtonActive: { borderColor: colors.danger, backgroundColor: colors.dangerSoft },
  micButtonText: { color: colors.primaryDark, fontSize: 18, fontWeight: '900' },
  micButtonTextActive: { color: colors.danger },
  compactActionButton: { width: 44, height: 42, borderRadius: 14 },
  sendCompact: { width: 48, height: 42, marginLeft: 'auto', borderRadius: 14 },
  shortActionButton: { width: 36, height: 40, borderRadius: 13 },
  sendShort: { width: 40, height: 40, marginLeft: 0, borderRadius: 13 },
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
