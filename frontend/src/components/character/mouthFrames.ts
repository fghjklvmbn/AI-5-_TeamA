import type { CharacterRig } from '../../character/manifest';

export const MOUTH_FRAME_COUNT = 30;

function smoothStep(value: number): number {
  return value * value * (3 - 2 * value);
}

export function createMouthFrames(
  talkingSprite: HTMLImageElement,
  rig: CharacterRig,
): HTMLCanvasElement[] {
  const width = 192;
  const sourceAspect = (rig.mouthPatchY * talkingSprite.naturalHeight)
    / (rig.mouthPatchX * talkingSprite.naturalWidth);
  const height = Math.max(96, Math.round(width * sourceAspect));
  const sourceX = talkingSprite.naturalWidth * (0.5 - rig.mouthPatchX);
  const sourceY = talkingSprite.naturalHeight * (rig.mouthY - rig.mouthPatchY);
  const sourceWidth = talkingSprite.naturalWidth * rig.mouthPatchX * 2;
  const sourceHeight = talkingSprite.naturalHeight * rig.mouthPatchY * 2;

  return Array.from({ length: MOUTH_FRAME_COUNT }, (_, index) => {
    const frame = document.createElement('canvas');
    frame.width = width;
    frame.height = height;
    if (index === 0) return frame;
    const frameContext = frame.getContext('2d');
    if (!frameContext) return frame;
    const opening = smoothStep(index / (MOUTH_FRAME_COUNT - 1));
    const verticalScale = 0.3 + opening * 0.7;
    const horizontalScale = 0.96 + Math.sin(opening * Math.PI) * 0.04;
    const drawWidth = width * horizontalScale;
    const drawHeight = height * verticalScale;
    frameContext.globalAlpha = 0.2 + opening * 0.8;
    frameContext.drawImage(
      talkingSprite,
      sourceX, sourceY, sourceWidth, sourceHeight,
      (width - drawWidth) / 2,
      (height - drawHeight) / 2 + height * (1 - verticalScale) * 0.08,
      drawWidth, drawHeight,
    );

    frameContext.globalCompositeOperation = 'destination-in';
    const horizontalMask = frameContext.createLinearGradient(0, 0, width, 0);
    horizontalMask.addColorStop(0, '#00000000');
    horizontalMask.addColorStop(0.18, '#000000FF');
    horizontalMask.addColorStop(0.82, '#000000FF');
    horizontalMask.addColorStop(1, '#00000000');
    frameContext.fillStyle = horizontalMask;
    frameContext.fillRect(0, 0, width, height);
    const verticalMask = frameContext.createLinearGradient(0, 0, 0, height);
    verticalMask.addColorStop(0, '#00000000');
    verticalMask.addColorStop(0.2, '#000000FF');
    verticalMask.addColorStop(0.8, '#000000FF');
    verticalMask.addColorStop(1, '#00000000');
    frameContext.fillStyle = verticalMask;
    frameContext.fillRect(0, 0, width, height);
    return frame;
  });
}
