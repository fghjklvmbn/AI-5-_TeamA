import type { CharacterCue } from '../../types';

export type CharacterMotion = {
  offsetX: number;
  offsetY: number;
  rotation: number;
  scale: number;
};

export function characterMotionFor(
  cue: CharacterCue | null | undefined,
  speaking: boolean,
  timestamp: number,
): CharacterMotion {
  if (!cue) return { offsetX: 0, offsetY: 0, rotation: 0, scale: 1 };
  const intensity = Math.min(1, Math.max(0, cue.intensity)) * (speaking ? 1 : 0.2);
  if (cue.gesture === 'celebrate') {
    return {
      offsetX: Math.sin(timestamp / 150) * 4 * intensity,
      offsetY: -Math.abs(Math.sin(timestamp / 190)) * 8 * intensity,
      rotation: Math.sin(timestamp / 210) * 0.025 * intensity,
      scale: 1 + Math.abs(Math.sin(timestamp / 190)) * 0.012 * intensity,
    };
  }
  if (cue.gesture === 'nod') {
    return { offsetX: 0, offsetY: Math.sin(timestamp / 240) * 3 * intensity, rotation: 0, scale: 1 };
  }
  if (cue.gesture === 'comfort') {
    return {
      offsetX: Math.sin(timestamp / 900) * 2 * intensity,
      offsetY: 2 * intensity,
      rotation: Math.sin(timestamp / 1100) * 0.012 * intensity,
      scale: 1 - 0.004 * intensity,
    };
  }
  return { offsetX: 0, offsetY: 0, rotation: 0, scale: 1 };
}
