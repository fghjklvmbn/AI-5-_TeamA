import { publishCharacterAudioState, subscribeCharacterAudio } from './audioPlayback';

test('audio state remains owned by the message that is actually playing', () => {
  const events: Array<[number, boolean, string | undefined]> = [];
  const unsubscribe = subscribeCharacterAudio((level, playing, messageId) => {
    events.push([level, playing, messageId]);
  });

  publishCharacterAudioState(0.7, true, 'message-a');
  publishCharacterAudioState(0, false, 'message-b');
  expect(events.at(-1)).toEqual([0.7, true, 'message-a']);

  publishCharacterAudioState(0, false, 'message-a');
  expect(events.at(-1)).toEqual([0, false, undefined]);
  unsubscribe();
});
