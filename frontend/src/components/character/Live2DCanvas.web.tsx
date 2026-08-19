import React, { useEffect, useRef } from 'react';

import { subscribeCharacterAudio } from '../../audioPlayback';
import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';

type Props = { characterId: CharacterId; activity: CharacterActivity; cue?: CharacterCue | null };

const PALETTES = {
  haru: { hair: '#49366F', skin: '#F7D7C4', outfit: '#8F6AE8', eye: '#332746' },
  nari: { hair: '#6A394C', skin: '#F5D1C4', outfit: '#D16E9E', eye: '#3D2730' },
} as const;

export default function Live2DCanvas({ characterId, activity, cue }: Props) {
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
  }, [characterId]);

  return <canvas aria-label={`${characterId} 실시간 2D 캐릭터`} ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
}
