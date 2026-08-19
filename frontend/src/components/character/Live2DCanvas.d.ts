import type { ComponentType } from 'react';

import type { CharacterActivity, CharacterCue, CharacterId } from '../../types';

declare const Live2DCanvas: ComponentType<{
  characterId: CharacterId;
  activity: CharacterActivity;
  cue?: CharacterCue | null;
  spriteUri?: string;
}>;

export default Live2DCanvas;
