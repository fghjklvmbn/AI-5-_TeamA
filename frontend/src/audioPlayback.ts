import { Platform } from 'react-native';

const SILENT_WAV = 'data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';

let sharedWebAudio: HTMLAudioElement | undefined;

function getWebAudio(): HTMLAudioElement | undefined {
  if (Platform.OS !== 'web' || typeof Audio === 'undefined') return undefined;
  sharedWebAudio ??= new Audio();
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

export async function playWebAudio(uri: string): Promise<void> {
  const audio = getWebAudio();
  if (!audio) return;
  audio.pause();
  audio.src = uri;
  audio.volume = 1;
  try {
    await audio.play();
  } catch (reason) {
    const error = reason as { name?: string };
    if (error?.name === 'NotAllowedError') {
      throw new Error('브라우저가 자동 음성 재생을 차단했어요. 아래 음성 듣기 버튼을 한 번 눌러 주세요.');
    }
    throw reason;
  }
}
