import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api, type AIPipelineTrace } from '../api';

const RECORDING_OPTIONS = {
  ...RecordingPresets.HIGH_QUALITY,
  isMeteringEnabled: true,
};

export function useLiveRecorder(token: string) {
  const recorder = useAudioRecorder(RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 100);
  const [isRecording, setIsRecording] = useState(false);
  const [amplitude, setAmplitude] = useState(0.12);
  const [liveText, setLiveText] = useState('');
  const mountedRef = useRef(true);
  const recordingRef = useRef(false);
  const recordingModeRef = useRef(false);
  const transitionRef = useRef(false);
  const transcriptionControllerRef = useRef<AbortController | undefined>(undefined);
  const operationVersionRef = useRef(0);
  const operationCompletionRef = useRef<Promise<void> | undefined>(undefined);

  const restorePlaybackMode = useCallback(async () => {
    if (!recordingModeRef.current) return;
    recordingModeRef.current = false;
    try {
      await setAudioModeAsync({ allowsRecording: false });
    } catch {
      // There is no useful UI to update during teardown; the next playback also sets its own mode.
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      operationVersionRef.current += 1;
      transcriptionControllerRef.current?.abort();
      transcriptionControllerRef.current = undefined;
      const stopPending = recordingRef.current
        ? recorder.stop().catch(() => undefined)
        : Promise.resolve();
      recordingRef.current = false;
      transitionRef.current = false;
      void stopPending.finally(() => restorePlaybackMode());
    };
  }, [recorder, restorePlaybackMode]);

  useEffect(() => {
    if (typeof recorderState.metering === 'number') {
      setAmplitude(Math.max(0.08, Math.min(1, 1 + recorderState.metering / 52)));
    }
  }, [recorderState.metering]);

  const start = useCallback(async () => {
    if (recordingRef.current || transitionRef.current) return;
    const operationVersion = ++operationVersionRef.current;
    let completeOperation: () => void = () => undefined;
    const operationCompletion = new Promise<void>((resolve) => { completeOperation = () => resolve(undefined); });
    operationCompletionRef.current = operationCompletion;
    transitionRef.current = true;
    try {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) throw new Error('음성 대화를 위해 마이크 권한을 허용해 주세요.');
      await setAudioModeAsync({
        allowsRecording: true,
        playsInSilentMode: true,
        shouldPlayInBackground: false,
      });
      recordingModeRef.current = true;
      if (!mountedRef.current || operationVersionRef.current !== operationVersion) return;
      setLiveText('');
      await recorder.prepareToRecordAsync();
      if (!mountedRef.current || operationVersionRef.current !== operationVersion) return;
      recorder.record();
      recordingRef.current = true;
      setIsRecording(true);
    } catch (reason) {
      if (!mountedRef.current || operationVersionRef.current !== operationVersion) return;
      recordingRef.current = false;
      setIsRecording(false);
      setAmplitude(0.12);
      throw reason;
    } finally {
      completeOperation();
      if (operationCompletionRef.current === operationCompletion) operationCompletionRef.current = undefined;
      if (operationVersionRef.current === operationVersion) transitionRef.current = false;
      if (!recordingRef.current) await restorePlaybackMode();
    }
  }, [recorder, restorePlaybackMode]);

  const stop = useCallback(async (trace?: AIPipelineTrace) => {
    if (transitionRef.current || !recordingRef.current) return '';
    const operationVersion = ++operationVersionRef.current;
    let completeOperation: () => void = () => undefined;
    const operationCompletion = new Promise<void>((resolve) => { completeOperation = () => resolve(undefined); });
    operationCompletionRef.current = operationCompletion;
    transitionRef.current = true;
    recordingRef.current = false;
    if (mountedRef.current) {
      setIsRecording(false);
      setAmplitude(0.12);
    }
    try {
      const uri = await (async (): Promise<string> => {
        try {
          await recorder.stop();
          const recordedUri = recorder.uri;
          if (!recordedUri) throw new Error('녹음 파일을 만들지 못했습니다. 다시 시도해 주세요.');
          return recordedUri;
        } finally {
          // Release the microphone before waiting for the transcription request.
          await restorePlaybackMode();
        }
      })();
      if (!mountedRef.current || operationVersionRef.current !== operationVersion) return '';
      const controller = new AbortController();
      transcriptionControllerRef.current = controller;
      let transcript: string;
      try {
        transcript = (await api.transcribe(token, uri, controller.signal, trace)).trim();
      } catch (reason) {
        if (!mountedRef.current || operationVersionRef.current !== operationVersion) return '';
        throw reason;
      } finally {
        if (transcriptionControllerRef.current === controller) transcriptionControllerRef.current = undefined;
      }
      if (!mountedRef.current || operationVersionRef.current !== operationVersion) return '';
      setLiveText(transcript);
      return transcript;
    } finally {
      completeOperation();
      if (operationCompletionRef.current === operationCompletion) operationCompletionRef.current = undefined;
      if (operationVersionRef.current === operationVersion) transitionRef.current = false;
    }
  }, [recorder, restorePlaybackMode, token]);

  const cancel = useCallback(async () => {
    const pendingOperation = operationCompletionRef.current;
    const operationVersion = ++operationVersionRef.current;
    transitionRef.current = true;
    transcriptionControllerRef.current?.abort();
    transcriptionControllerRef.current = undefined;
    const shouldStopRecorder = recordingRef.current;
    recordingRef.current = false;
    if (mountedRef.current) {
      setIsRecording(false);
      setAmplitude(0.12);
      setLiveText('');
    }
    try {
      if (pendingOperation) await pendingOperation;
      if (shouldStopRecorder) await recorder.stop();
    } catch {
      // Cancellation is best-effort; audio mode restoration still has to run.
    } finally {
      await restorePlaybackMode();
      if (operationVersionRef.current === operationVersion) transitionRef.current = false;
    }
  }, [recorder, restorePlaybackMode]);

  return {
    isRecording,
    amplitude,
    liveText,
    durationMillis: recorderState.durationMillis,
    start,
    stop,
    cancel,
  };
}
