import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { api } from '../api';
import { ConversationContextControls } from './ConversationContextControls';

jest.mock('../api', () => ({
  api: {
    loadModel: jest.fn(),
    localModels: jest.fn(),
    modelSelection: jest.fn(),
    voices: jest.fn(),
  },
}));

beforeEach(() => {
  jest.clearAllMocks();
  (api.modelSelection as jest.Mock).mockResolvedValue({
    model_key: 'hyperclovax-seed-text-instruct-1.5b', display_name: 'HyperCLOVA X', loaded: true,
  });
  (api.localModels as jest.Mock).mockResolvedValue({
    models: [
      { key: 'hyperclovax-seed-text-instruct-1.5b', display_name: 'HyperCLOVA X', loaded_instances: [{ id: 'instance-a' }] },
      { key: 'qwen3.5-4b', display_name: 'Qwen 3.5 4B', loaded_instances: [] },
      { key: 'downloaded-model-2b', display_name: 'Downloaded Model', loaded_instances: [] },
    ],
  });
  (api.loadModel as jest.Mock).mockResolvedValue({});
  (api.voices as jest.Mock).mockResolvedValue([
    { id: 'default', voice_name: '기본 음성', is_default: true, is_personalized: false },
    { id: 'voice-a', voice_name: '나의 음성', is_default: false, is_personalized: true },
  ]);
});

test('changes the persona from the chat context bar', async () => {
  const onPersonaChange = jest.fn().mockResolvedValue(undefined);
  render(
    <ConversationContextControls
      modelKey="hyperclovax-seed-text-instruct-1.5b"
      onModelKeyChange={jest.fn()}
      onPersonaChange={onPersonaChange}
      onVoiceIdChange={jest.fn()}
      persona="default"
      token="token"
    />,
  );

  fireEvent.press(screen.getByLabelText('대화 상세 설정 열기'));
  fireEvent.press(screen.getByLabelText('페르소나 선택, 현재 기본'));
  fireEvent.press(screen.getByLabelText('정서적 동반자 페르소나'));

  await waitFor(() => expect(onPersonaChange).toHaveBeenCalledWith('emotional_companion'));
});

test('loads and selects a downloaded model from the chat context bar', async () => {
  const onModelKeyChange = jest.fn().mockResolvedValue(undefined);
  render(
    <ConversationContextControls
      modelKey="hyperclovax-seed-text-instruct-1.5b"
      onModelKeyChange={onModelKeyChange}
      onPersonaChange={jest.fn()}
      onVoiceIdChange={jest.fn()}
      persona="default"
      token="token"
    />,
  );

  fireEvent.press(screen.getByLabelText('대화 상세 설정 열기'));
  fireEvent.press(await screen.findByLabelText('모델 선택, 현재 HyperCLOVA X'));
  fireEvent.press(await screen.findByLabelText('Qwen 3.5 4B 모델 선택'));

  await waitFor(() => expect(api.loadModel).toHaveBeenCalledWith('token', 'qwen3.5-4b', 40960));
  await waitFor(() => expect(onModelKeyChange).toHaveBeenCalledWith('qwen3.5-4b'));
});

test('selects a response voice from the chat context bar', async () => {
  const onVoiceIdChange = jest.fn();
  render(
    <ConversationContextControls
      modelKey="hyperclovax-seed-text-instruct-1.5b"
      onModelKeyChange={jest.fn()}
      onPersonaChange={jest.fn()}
      onVoiceIdChange={onVoiceIdChange}
      persona="default"
      token="token"
    />,
  );

  fireEvent.press(screen.getByLabelText('대화 상세 설정 열기'));
  fireEvent.press(screen.getByLabelText('응답 음성 선택, 현재 기본 음성'));
  fireEvent.press(await screen.findByLabelText('나의 음성 응답 음성 선택'));

  expect(onVoiceIdChange).toHaveBeenCalledWith('voice-a');
});

test('keeps advanced chat controls hidden until requested', () => {
  render(
    <ConversationContextControls
      modelKey="hyperclovax-seed-text-instruct-1.5b"
      onModelKeyChange={jest.fn()}
      onPersonaChange={jest.fn()}
      onVoiceIdChange={jest.fn()}
      persona="default"
      token="token"
    />,
  );

  expect(screen.queryByLabelText('페르소나 선택, 현재 기본')).toBeNull();
  fireEvent.press(screen.getByLabelText('대화 상세 설정 열기'));
  expect(screen.getByLabelText('페르소나 선택, 현재 기본')).toBeDefined();
  fireEvent.press(screen.getByLabelText('대화 상세 설정 닫기'));
  expect(screen.queryByLabelText('페르소나 선택, 현재 기본')).toBeNull();
});
