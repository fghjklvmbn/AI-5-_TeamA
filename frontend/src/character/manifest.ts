import type { CharacterId } from './ids';

export type CharacterRig = {
  fitWidth: number;
  fitHeight: number;
  offsetY: number;
  blink: boolean;
  eyeY: number;
  eyeSpread: number;
  eyeRadiusX: number;
  eyeRadiusY: number;
  mouthY: number;
  mouthPatchX: number;
  mouthPatchY: number;
  skin: string;
  skinCenter: string;
  line: string;
  mouth: string;
};

export type CharacterDefinition = {
  name: string;
  color: string;
  assets: { idle: number; talking: number };
  palette: { hair: string; skin: string; outfit: string; eye: string };
  rig: CharacterRig;
};

export const CHARACTER_MANIFEST: Record<CharacterId, CharacterDefinition> = {
  haru: {
    name: '메모리',
    color: '#8F6AE8',
    assets: {
      idle: require('../../assets/memory-mascot.png'),
      talking: require('../../assets/memory-talking.png'),
    },
    palette: { hair: '#49366F', skin: '#F7D7C4', outfit: '#8F6AE8', eye: '#332746' },
    rig: {
      fitWidth: 0.9, fitHeight: 0.91, offsetY: 7,
      blink: true,
      eyeY: 0.382, eyeSpread: 0.112, eyeRadiusX: 0.031, eyeRadiusY: 0.027,
      mouthY: 0.421, mouthPatchX: 0.064, mouthPatchY: 0.034,
      skin: '#F6D4C4', skinCenter: '#F7D7C7', line: '#5A315A', mouth: '#783F68',
    },
  },
  nari: {
    name: '나리',
    color: '#D16E9E',
    assets: {
      idle: require('../../assets/nari-assistant.png'),
      talking: require('../../assets/nari-talking.png'),
    },
    palette: { hair: '#6A394C', skin: '#F5D1C4', outfit: '#D16E9E', eye: '#3D2730' },
    rig: {
      fitWidth: 1.18, fitHeight: 1.75, offsetY: 125,
      blink: false,
      eyeY: 0.092, eyeSpread: 0.035, eyeRadiusX: 0.015, eyeRadiusY: 0.009,
      mouthY: 0.111, mouthPatchX: 0.026, mouthPatchY: 0.014,
      skin: '#F6D0C9', skinCenter: '#F7D3CC', line: '#935364', mouth: '#B76072',
    },
  },
};
