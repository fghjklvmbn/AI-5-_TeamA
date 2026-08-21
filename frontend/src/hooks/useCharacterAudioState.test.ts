import { characterCueForPlayback } from './useCharacterAudioState';
import type { CharacterCue, Message } from '../types';

const calm: CharacterCue = { emotion: 'neutral', intensity: 0.3, gesture: 'idle', voice_style: 'calm' };
const happy: CharacterCue = { emotion: 'happy', intensity: 0.8, gesture: 'celebrate', voice_style: 'bright' };
const messages: Message[] = [
  { id: 'first', user_text: 'a', assistant_text: 'a', created_at: '1', character_cue: calm },
  { id: 'second', user_text: 'b', assistant_text: 'b', created_at: '2', character_cue: happy },
];

test('uses the cue belonging to the playing message', () => {
  expect(characterCueForPlayback(messages, 'first')).toEqual(calm);
});

test('falls back to the latest cue when no message is playing', () => {
  expect(characterCueForPlayback(messages)).toEqual(happy);
});
