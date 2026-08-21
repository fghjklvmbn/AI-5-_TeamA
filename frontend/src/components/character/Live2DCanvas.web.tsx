import React, { useEffect, useRef } from 'react';

import { subscribeCharacterAudio } from '../../audioPlayback';
import { CHARACTER_MANIFEST } from '../../character/manifest';
import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';
import { characterMotionFor } from './characterMotion';
import { advanceMouthAnimation, INITIAL_MOUTH_ANIMATION } from './mouthAnimation';
import { createMouthFrames, MOUTH_FRAME_COUNT } from './mouthFrames';

type Props = {
  characterId: CharacterId;
  activity: CharacterActivity;
  cue?: CharacterCue | null;
  spriteUri?: string;
  talkingSpriteUri?: string;
};

export default function Live2DCanvas({ characterId, activity, cue, spriteUri, talkingSpriteUri }: Props) {
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
    let talkingSpriteReady = false;
    let mouthFrames: HTMLCanvasElement[] = [];
    let mouthAnimation = INITIAL_MOUTH_ANIMATION;
    const sprite = spriteUri ? new window.Image() : null;
    const talkingSprite = talkingSpriteUri ? new window.Image() : null;
    const prepareMouthFrames = () => {
      if (spriteReady && talkingSpriteReady && talkingSprite) {
        mouthFrames = createMouthFrames(talkingSprite, CHARACTER_MANIFEST[characterId].rig);
      }
    };
    if (sprite && spriteUri) {
      sprite.decoding = 'async';
      sprite.onload = () => { spriteReady = true; prepareMouthFrames(); };
      sprite.src = spriteUri;
    }
    if (talkingSprite && talkingSpriteUri) {
      talkingSprite.decoding = 'async';
      talkingSprite.onload = () => { talkingSpriteReady = true; prepareMouthFrames(); };
      talkingSprite.src = talkingSpriteUri;
    }
    const palette = CHARACTER_MANIFEST[characterId].palette;
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
      mouthAnimation = advanceMouthAnimation(mouthAnimation, {
        speaking,
        playing: playingRef.current,
        audioLevel: audioLevelRef.current,
        timestamp,
      });
      const mouth = mouthAnimation.position / (MOUTH_FRAME_COUNT - 1);
      const emotion = cueRef.current?.emotion ?? 'neutral';
      const cueIntensity = Math.min(1, Math.max(0, cueRef.current?.intensity ?? 0));
      const motion = characterMotionFor(cueRef.current, speaking, timestamp);

      if (sprite && spriteReady) {
        const rig = CHARACTER_MANIFEST[characterId].rig;
        const fittedScale = Math.min((width * rig.fitWidth) / sprite.naturalWidth, (height * rig.fitHeight) / sprite.naturalHeight);
        const spriteWidth = sprite.naturalWidth * fittedScale;
        const spriteHeight = sprite.naturalHeight * fittedScale;
        const sway = thinking * 0.0025 + Math.sin(timestamp / 2200) * 0.008;
        const breathingScale = 1 + Math.sin(timestamp / 850) * 0.006;
        context.save();
        context.translate(
          width / 2 + thinking + motion.offsetX,
          height / 2 + breath * 0.55 + rig.offsetY + motion.offsetY,
        );
        context.rotate(sway + motion.rotation);
        context.scale(breathingScale * motion.scale, breathingScale * motion.scale);
        context.drawImage(sprite, -spriteWidth / 2, -spriteHeight / 2, spriteWidth, spriteHeight);

        const top = -spriteHeight / 2;
        const eyeY = top + spriteHeight * rig.eyeY;
        const leftEyeX = -spriteWidth * rig.eyeSpread;
        const rightEyeX = spriteWidth * rig.eyeSpread;
        if (rig.blink && blink > 0.18) {
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

        if (mouthFrames.length === MOUTH_FRAME_COUNT && mouthAnimation.position >= 0.5) {
          const mouthY = top + spriteHeight * rig.mouthY;
          const mouthFrame = mouthFrames[Math.min(MOUTH_FRAME_COUNT - 1, Math.round(mouthAnimation.position))];
          const patchWidth = spriteWidth * rig.mouthPatchX * 2;
          const patchHeight = spriteHeight * rig.mouthPatchY * 2;
          if (mouthFrame) context.drawImage(mouthFrame, -patchWidth / 2, mouthY - patchHeight / 2, patchWidth, patchHeight);
        }

        if ((emotion === 'happy' || emotion === 'excited') && cueIntensity > 0) {
          context.save();
          context.globalAlpha = (speaking ? 0.18 : 0.05) * cueIntensity;
          context.fillStyle = '#F28F9D';
          for (const cheekX of [-spriteWidth * (rig.eyeSpread + 0.045), spriteWidth * (rig.eyeSpread + 0.045)]) {
            context.beginPath();
            context.ellipse(cheekX, eyeY + spriteHeight * 0.04, spriteWidth * 0.035, spriteHeight * 0.012, 0, 0, Math.PI * 2);
            context.fill();
          }
          context.restore();
        } else if ((emotion === 'sad' || emotion === 'concerned') && cueIntensity > 0) {
          context.save();
          context.globalAlpha = (speaking ? 0.5 : 0.15) * cueIntensity;
          context.strokeStyle = rig.line;
          context.lineWidth = Math.max(1.5, spriteWidth * 0.004);
          for (const direction of [-1, 1]) {
            const eyeX = direction * spriteWidth * rig.eyeSpread;
            context.beginPath();
            context.moveTo(eyeX - spriteWidth * 0.022, eyeY - spriteHeight * 0.027 + direction * spriteHeight * 0.004);
            context.quadraticCurveTo(eyeX, eyeY - spriteHeight * 0.038, eyeX + spriteWidth * 0.022, eyeY - spriteHeight * 0.027 - direction * spriteHeight * 0.004);
            context.stroke();
          }
          context.restore();
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
  }, [characterId, spriteUri, talkingSpriteUri]);

  return <canvas aria-label={`${characterId} 실시간 2D 캐릭터`} ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
}
