import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useEffect, useRef, useState } from 'react';

import { api } from '../api';

const SEGMENT_MS = 2500;
const LIVE_RECORDING_OPTIONS = {
  ...RecordingPresets.HIGH_QUALITY,
  isMeteringEnabled: true,
};

export function useLiveRecorder(token: string) {
  const recorder = useAudioRecorder(LIVE_RECORDING_OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 100);
  const activeRef = useRef(false);
  const rotateRef = useRef<() => Promise<void>>(async () => undefined);
  const rotatingRef = useRef<Promise<void> | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transcriptsRef = useRef<string[]>([]);
  const uploadsRef = useRef<Promise<void>[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [amplitude, setAmplitude] = useState(0.12);
  const [liveText, setLiveText] = useState('');

  useEffect(() => {
    if (typeof recorderState.metering === 'number') {
      setAmplitude(Math.max(0.08, Math.min(1, 1 + recorderState.metering / 52)));
    }
  }, [recorderState.metering]);

  const uploadSegment = useCallback(
    async (uri: string) => {
      const text = (await api.transcribe(token, uri)).trim();
      if (text) {
        transcriptsRef.current.push(text);
        setLiveText(transcriptsRef.current.join(' '));
      }
    },
    [token],
  );

  const beginSegment = useCallback(async function begin(): Promise<void> {
    if (!activeRef.current) return;
    await recorder.prepareToRecordAsync();
    recorder.record();
    timerRef.current = setTimeout(() => void rotateRef.current(), SEGMENT_MS);
  }, [recorder]);

  const rotateSegment = useCallback(async function rotate(): Promise<void> {
    if (rotatingRef.current) return rotatingRef.current;
    const task = (async () => {
      try {
        await recorder.stop();
        const uri = recorder.uri;
        if (activeRef.current) await beginSegment();
        if (uri) uploadsRef.current.push(uploadSegment(uri).catch(() => undefined));
      } catch {
        if (activeRef.current) await beginSegment();
      }
    })();
    rotatingRef.current = task;
    try {
      await task;
    } finally {
      rotatingRef.current = null;
    }
  }, [beginSegment, recorder, uploadSegment]);

  rotateRef.current = rotateSegment;

  const start = useCallback(async () => {
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) throw new Error('실시간 대화를 위해 마이크 권한을 허용해 주세요.');
    await setAudioModeAsync({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
    });
    transcriptsRef.current = [];
    uploadsRef.current = [];
    setLiveText('');
    activeRef.current = true;
    setIsRecording(true);
    await beginSegment();
  }, [beginSegment]);

  const stop = useCallback(async () => {
    activeRef.current = false;
    setIsRecording(false);
    setAmplitude(0.12);
    if (timerRef.current) clearTimeout(timerRef.current);
    await rotateSegment();
    if (recorder.getStatus().isRecording) await rotateSegment();
    await Promise.all(uploadsRef.current);
    await setAudioModeAsync({ allowsRecording: false });
    return transcriptsRef.current.join(' ').trim();
  }, [rotateSegment]);

  return { isRecording, amplitude, liveText, start, stop };
}
