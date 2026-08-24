import React from 'react';
import { render, screen, waitFor } from '@testing-library/react-native';

import { MessageAudioButton } from './MessageAudioButton';

const mockSeekTo = jest.fn(async () => undefined);
const mockPlay = jest.fn();

jest.mock('expo-audio', () => ({
  useAudioPlayer: () => ({ seekTo: mockSeekTo, play: mockPlay }),
  useAudioPlayerStatus: () => ({ playing: false }),
}));

jest.mock('../audioPlayback', () => ({
  playWebAudio: jest.fn(async () => undefined),
  publishCharacterAudioState: jest.fn(),
}));

beforeEach(() => {
  mockSeekTo.mockClear();
  mockPlay.mockClear();
});

test('hidden live-mode player automatically starts audio without rendering controls', async () => {
  render(
    <MessageAudioButton
      autoPlay
      controls={false}
      messageId="live-message"
      onError={jest.fn()}
      uri="https://example.com/live-message.wav"
    />,
  );

  expect(screen.queryByText('▶ 음성으로 듣기')).toBeNull();
  await waitFor(() => expect(mockPlay).toHaveBeenCalledTimes(1));
});

test('visible audio control does not play until requested when autoplay is disabled', () => {
  render(
    <MessageAudioButton
      messageId="chat-message"
      onError={jest.fn()}
      uri="https://example.com/chat-message.wav"
    />,
  );

  expect(screen.getByText('▶ 음성으로 듣기')).toBeDefined();
  expect(mockPlay).not.toHaveBeenCalled();
});
