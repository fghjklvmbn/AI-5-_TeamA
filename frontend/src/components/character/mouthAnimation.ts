import { MOUTH_FRAME_COUNT } from './mouthFrames';

export type MouthAnimationState = { position: number; velocity: number };

export const INITIAL_MOUTH_ANIMATION: MouthAnimationState = { position: 0, velocity: 0 };

export function advanceMouthAnimation(
  current: MouthAnimationState,
  input: { speaking: boolean; playing: boolean; audioLevel: number; timestamp: number },
): MouthAnimationState {
  const fallbackMouth = input.speaking && !input.playing
    ? 0.18 + Math.max(0, Math.sin(input.timestamp / 185)) * 0.2
    : 0;
  const audioMouth = input.playing
    ? Math.min(1, Math.max(0, (input.audioLevel - 0.025) * 2.25))
    : fallbackMouth;
  const target = input.speaking ? audioMouth * (MOUTH_FRAME_COUNT - 1) : 0;
  let velocity = current.velocity + (target - current.position) * 0.2;
  velocity *= target > current.position ? 0.62 : 0.72;
  const position = Math.max(0, Math.min(MOUTH_FRAME_COUNT - 1, current.position + velocity));
  return { position, velocity };
}
