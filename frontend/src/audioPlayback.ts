import { Platform } from 'react-native';

const SILENT_WAV = 'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

let sharedWebAudio: HTMLAudioElement | undefined;
let webAudioContext: AudioContext | undefined;
let webAudioAnalyser: AnalyserNode | undefined;
let webAudioSource: MediaElementAudioSourceNode | undefined;
let animationFrame: number | undefined;
let smoothedCharacterLevel = 0;
let currentCharacterLevel = 0;
let characterAudioPlaying = false;
let currentCharacterMessageId: string | undefined;
const characterAudioListeners = new Set<(level: number, playing: boolean, messageId?: string) => void>();

export function publishCharacterAudioState(level: number, playing: boolean, messageId?: string): void {
  if (!playing && messageId && currentCharacterMessageId && messageId !== currentCharacterMessageId) return;
  currentCharacterLevel = level;
  characterAudioPlaying = playing;
  currentCharacterMessageId = playing ? (messageId ?? currentCharacterMessageId) : undefined;
  characterAudioListeners.forEach((listener) => listener(level, playing, currentCharacterMessageId));
}

export function subscribeCharacterAudio(listener: (level: number, playing: boolean, messageId?: string) => void): () => void {
  characterAudioListeners.add(listener);
  listener(currentCharacterLevel, characterAudioPlaying, currentCharacterMessageId);
  return () => characterAudioListeners.delete(listener);
}

function stopLevelSampling(): void {
  if (animationFrame !== undefined && typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(animationFrame);
  animationFrame = undefined;
  smoothedCharacterLevel = 0;
  publishCharacterAudioState(0, false, currentCharacterMessageId);
}

function startLevelSampling(): void {
  const analyser = webAudioAnalyser;
  if (!analyser || typeof requestAnimationFrame === 'undefined') {
    publishCharacterAudioState(0.45, true, currentCharacterMessageId);
    return;
  }
  const samples = new Uint8Array(analyser.frequencyBinCount);
  const sample = () => {
    if (!sharedWebAudio || sharedWebAudio.paused || sharedWebAudio.ended) {
      stopLevelSampling();
      return;
    }
    analyser.getByteTimeDomainData(samples);
    let energy = 0;
    for (const value of samples) {
      const centered = (value - 128) / 128;
      energy += centered * centered;
    }
    const rawLevel = Math.min(1, Math.sqrt(energy / samples.length) * 4.5);
    const gatedLevel = rawLevel < 0.035 ? 0 : (rawLevel - 0.035) / 0.965;
    const smoothing = gatedLevel > smoothedCharacterLevel ? 0.42 : 0.2;
    smoothedCharacterLevel += (gatedLevel - smoothedCharacterLevel) * smoothing;
    publishCharacterAudioState(smoothedCharacterLevel, true, currentCharacterMessageId);
    animationFrame = requestAnimationFrame(sample);
  };
  sample();
}

function getWebAudio(): HTMLAudioElement | undefined {
  if (Platform.OS !== 'web' || typeof Audio === 'undefined') return undefined;
  if (!sharedWebAudio) {
    sharedWebAudio = new Audio();
    sharedWebAudio.crossOrigin = 'anonymous';
    sharedWebAudio.addEventListener('ended', stopLevelSampling);
    sharedWebAudio.addEventListener('pause', stopLevelSampling);
    try {
      webAudioContext = new AudioContext();
      webAudioAnalyser = webAudioContext.createAnalyser();
      webAudioAnalyser.fftSize = 256;
      webAudioSource = webAudioContext.createMediaElementSource(sharedWebAudio);
      webAudioSource.connect(webAudioAnalyser);
      webAudioAnalyser.connect(webAudioContext.destination);
    } catch {
      webAudioContext = undefined;
      webAudioAnalyser = undefined;
      webAudioSource = undefined;
    }
  }
  return sharedWebAudio;
}

/** Call synchronously from a click/tap so a later server response may auto-play. */
export function unlockWebAudio(): void {
  const audio = getWebAudio();
  if (!audio || !audio.paused) return;
  audio.src = SILENT_WAV;
  audio.volume = 0.01;
  void audio.play().catch(() => undefined);
}

export async function playWebAudio(uri: string, messageId?: string): Promise<void> {
  const audio = getWebAudio();
  if (!audio) return;
  audio.pause();
  currentCharacterMessageId = messageId;
  audio.src = uri;
  audio.volume = 1;
  try {
    if (webAudioContext?.state === 'suspended') await webAudioContext.resume();
    await audio.play();
    startLevelSampling();
  } catch (reason) {
    const error = reason as { name?: string };
    if (error?.name === 'NotAllowedError') {
      throw new Error('브라우저가 자동 음성 재생을 차단했어요. 아래 음성 듣기 버튼을 한 번 눌러 주세요.');
    }
    throw reason;
  }
}
