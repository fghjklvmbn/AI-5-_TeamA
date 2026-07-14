import {
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from 'expo-audio';
import { useCallback, useEffect, useState } from 'react';

import { api } from '../api';

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

  useEffect(() => {
    if (typeof recorderState.metering === 'number') {
      setAmplitude(Math.max(0.08, Math.min(1, 1 + recorderState.metering / 52)));
    }
  }, [recorderState.metering]);

  const start = useCallback(async () => {
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) throw new Error('음성 대화를 위해 마이크 권한을 허용해 주세요.');
    await setAudioModeAsync({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldPlayInBackground: false,
    });
    setLiveText('');
    await recorder.prepareToRecordAsync();
    recorder.record();
    setIsRecording(true);
  }, [recorder]);

  const stop = useCallback(async () => {
    setIsRecording(false);
    setAmplitude(0.12);
    try {
      await recorder.stop();
      const uri = recorder.uri;
      if (!uri) throw new Error('녹음 파일을 만들지 못했습니다. 다시 시도해 주세요.');
      const transcript = (await api.transcribe(token, uri)).trim();
      setLiveText(transcript);
      return transcript;
    } finally {
      await setAudioModeAsync({ allowsRecording: false });
    }
  }, [recorder, token]);

  return {
    isRecording,
    amplitude,
    liveText,
    durationMillis: recorderState.durationMillis,
    start,
    stop,
  };
}
