import { useEffect, useState } from 'react';

import { subscribeCharacterAudio } from '../audioPlayback';
import type { Message } from '../types';

export function characterCueForPlayback(messages: Message[], messageId?: string) {
  const playingCue = messageId
    ? messages.find((message) => message.id === messageId)?.character_cue
    : undefined;
  return playingCue
    ?? [...messages].reverse().find((message) => message.character_cue)?.character_cue;
}

export function useCharacterAudioState() {
  const [playing, setPlaying] = useState(false);
  const [messageId, setMessageId] = useState<string>();

  useEffect(() => subscribeCharacterAudio((_level, nextPlaying, nextMessageId) => {
    setPlaying(nextPlaying);
    setMessageId(nextPlaying ? nextMessageId : undefined);
  }), []);

  return { playing, messageId };
}
