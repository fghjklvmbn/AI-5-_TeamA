import React, { useEffect, useRef } from 'react';

import { subscribeCharacterAudio } from '../../audioPlayback';
import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';

type Props = {
  characterId: CharacterId;
  activity: CharacterActivity;
  cue?: CharacterCue | null;
  spriteUri?: string;
};

const PALETTES = {
  haru: { hair: '#49366F', skin: '#F7D7C4', outfit: '#8F6AE8', eye: '#332746' },
  nari: { hair: '#6A394C', skin: '#F5D1C4', outfit: '#D16E9E', eye: '#3D2730' },
} as const;

const SPRITE_RIGS = {
  haru: {
    fitWidth: 0.9, fitHeight: 0.91, offsetY: 7,
    eyeY: 0.382, eyeSpread: 0.112, eyeRadiusX: 0.031, eyeRadiusY: 0.027,
    mouthY: 0.421, mouthPatchX: 0.058, mouthPatchY: 0.028,
    skin: '#F6D4C4', skinCenter: '#F7D7C7', line: '#5A315A', mouth: '#783F68',
  },
  nari: {
    fitWidth: 0.98, fitHeight: 1.5, offsetY: 78,
    eyeY: 0.105, eyeSpread: 0.044, eyeRadiusX: 0.018, eyeRadiusY: 0.012,
    mouthY: 0.13, mouthPatchX: 0.028, mouthPatchY: 0.014,
    skin: '#F6D0C9', skinCenter: '#F7D3CC', line: '#935364', mouth: '#B76072',
  },
} as const;

export default function Live2DCanvas({ characterId, activity, cue, spriteUri }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const audioLevelRef = useRef(0);
  const playingRef = useRef(false);
  const activityRef = useRef(activity);
  const cueRef = useRef(cue);
  activityRef.current = activity;
  cueRef.current = cue;

  useEffect(() => subscribeCharacterAudio((level, playing) => {
    audioLevelRef.current = level;
    playingRef.current = playing;
  }), []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;
    let frame = 0;
    let spriteReady = false;
    const sprite = spriteUri ? new window.Image() : null;
    if (sprite && spriteUri) {
      sprite.decoding = 'async';
      sprite.onload = () => { spriteReady = true; };
      sprite.src = spriteUri;
    }
    const palette = PALETTES[characterId];
    const render = (timestamp: number) => {
      const width = canvas.clientWidth || 360;
      const height = canvas.clientHeight || 520;
      const scale = window.devicePixelRatio || 1;
      if (canvas.width !== Math.round(width * scale) || canvas.height !== Math.round(height * scale)) {
        canvas.width = Math.round(width * scale);
        canvas.height = Math.round(height * scale);
      }
      context.setTransform(scale, 0, 0, scale, 0, 0);
      context.clearRect(0, 0, width, height);
      const breath = Math.sin(timestamp / 850) * 3;
      const thinking = activityRef.current === 'thinking' ? Math.sin(timestamp / 420) * 5 : 0;
      const x = width / 2 + thinking;
      const faceY = height * 0.38 + breath;
      const blinkCycle = timestamp % 4200;
      const blink = blinkCycle > 4080 ? Math.max(0.5, (blinkCycle - 4080) / 80) : 0;
      const speaking = activityRef.current === 'speaking' || playingRef.current;
      const fallbackMouth = speaking ? (Math.sin(timestamp / 70) + 1) / 2 : 0;
      const mouth = Math.max(audioLevelRef.current, fallbackMouth * 0.58);
      const emotion = cueRef.current?.emotion ?? 'neutral';

      if (sprite && spriteReady) {
        const rig = SPRITE_RIGS[characterId];
        const fittedScale = Math.min((width * rig.fitWidth) / sprite.naturalWidth, (height * rig.fitHeight) / sprite.naturalHeight);
        const spriteWidth = sprite.naturalWidth * fittedScale;
        const spriteHeight = sprite.naturalHeight * fittedScale;
        const sway = thinking * 0.0025 + Math.sin(timestamp / 2200) * 0.008;
        const breathingScale = 1 + Math.sin(timestamp / 850) * 0.006;
        context.save();
        context.translate(width / 2 + thinking, height / 2 + breath * 0.55 + rig.offsetY);
        context.rotate(sway);
        context.scale(breathingScale, breathingScale);
        context.drawImage(sprite, -spriteWidth / 2, -spriteHeight / 2, spriteWidth, spriteHeight);

        const top = -spriteHeight / 2;
        const eyeY = top + spriteHeight * rig.eyeY;
        const leftEyeX = -spriteWidth * rig.eyeSpread;
        const rightEyeX = spriteWidth * rig.eyeSpread;
        if (blink > 0.18) {
          context.fillStyle = rig.skin;
          for (const eyeX of [leftEyeX, rightEyeX]) {
            context.beginPath();
            context.ellipse(eyeX, eyeY, spriteWidth * rig.eyeRadiusX, spriteHeight * rig.eyeRadiusY, 0, 0, Math.PI * 2);
            context.fill();
            context.strokeStyle = rig.line;
            context.lineWidth = Math.max(2, spriteWidth * 0.006);
            context.beginPath();
            context.moveTo(eyeX - spriteWidth * 0.021, eyeY);
            context.quadraticCurveTo(eyeX, eyeY + spriteHeight * 0.008, eyeX + spriteWidth * 0.021, eyeY);
            context.stroke();
          }
        }

        const mouthY = top + spriteHeight * rig.mouthY;
        const patch = context.createRadialGradient(0, mouthY, 1, 0, mouthY, spriteWidth * rig.mouthPatchX);
        patch.addColorStop(0, rig.skinCenter);
        patch.addColorStop(1, `${rig.skinCenter}00`);
        context.fillStyle = patch;
        context.beginPath();
        context.ellipse(0, mouthY, spriteWidth * rig.mouthPatchX, spriteHeight * rig.mouthPatchY, 0, 0, Math.PI * 2);
        context.fill();
        context.strokeStyle = rig.line;
        context.fillStyle = rig.mouth;
        context.lineWidth = Math.max(2, spriteWidth * 0.006);
        if (speaking) {
          context.beginPath();
          context.ellipse(0, mouthY + spriteHeight * 0.004, spriteWidth * (0.015 + mouth * 0.017), spriteHeight * (0.004 + mouth * 0.017), 0, 0, Math.PI * 2);
          context.fill();
        } else {
          context.beginPath();
          context.moveTo(-spriteWidth * 0.028, mouthY - spriteHeight * 0.003);
          context.quadraticCurveTo(0, mouthY + spriteHeight * (emotion === 'sad' ? -0.009 : 0.012), spriteWidth * 0.028, mouthY - spriteHeight * 0.003);
          context.stroke();
        }
        context.restore();
        frame = requestAnimationFrame(render);
        return;
      }

      context.fillStyle = palette.outfit;
      context.beginPath();
      context.ellipse(x, height * 0.84, width * 0.28, height * 0.28 + breath, 0, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = palette.hair;
      context.beginPath();
      context.ellipse(x, faceY - 16, 102, 137, 0, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = palette.skin;
      context.beginPath();
      context.ellipse(x, faceY, 76, 102, 0, 0, Math.PI * 2);
      context.fill();

      context.strokeStyle = palette.eye;
      context.lineWidth = 5;
      const eyeY = faceY - 17;
      for (const direction of [-1, 1]) {
        context.beginPath();
        context.moveTo(x + direction * 47, eyeY);
        context.quadraticCurveTo(x + direction * 31, eyeY + (emotion === 'happy' || emotion === 'excited' ? -4 : 1), x + direction * 18, eyeY);
        if (blink < 0.6) context.stroke();
      }
      context.fillStyle = '#D98787';
      context.beginPath();
      context.ellipse(x, faceY + 42, 11 + mouth * 9, 3 + mouth * 13, 0, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = '#FFFFFF66';
      context.lineWidth = 3;
      context.beginPath();
      context.arc(x, faceY + 45, 29, 0.22, Math.PI - 0.22);
      if (emotion === 'happy' || emotion === 'excited') context.stroke();
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frame);
  }, [characterId, spriteUri]);

  return <canvas aria-label={`${characterId} 실시간 2D 캐릭터`} ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
}
