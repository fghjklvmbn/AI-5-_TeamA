import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { api } from '../api';
import { ModelManager } from './ModelManager';

jest.mock('../api', () => ({
  api: {
    modelManagerStatus: jest.fn(),
    localModels: jest.fn(),
    modelDownloads: jest.fn(),
    loadModel: jest.fn(),
    modelDownloadStatus: jest.fn(),
  },
}));

const models = [
  { key: 'model-a', display_name: 'Model A', loaded_instances: [] },
  { key: 'model-b', display_name: 'Model B', loaded_instances: [] },
];

beforeEach(() => {
  (api.modelManagerStatus as jest.Mock).mockResolvedValue({ server_online: true, model_count: 2, checked_at: '' });
  (api.localModels as jest.Mock).mockResolvedValue({ models });
  (api.modelDownloads as jest.Mock).mockResolvedValue({ jobs: [], quota_bytes: 10, used_bytes: 0 });
});

test('shows loading text and disables every downloaded model while a model loads', async () => {
  let finishLoad: (() => void) | undefined;
  (api.loadModel as jest.Mock).mockReturnValue(new Promise<void>((resolve) => { finishLoad = resolve; }));
  const onSelectedModelKeyChange = jest.fn();
  render(<ModelManager token="token" onSelectedModelKeyChange={onSelectedModelKeyChange} />);

  fireEvent.press(await screen.findByLabelText('직접 모델 관리 상세 펼치기'));
  const firstLoad = await screen.findByLabelText('Model A 로드');
  fireEvent.press(firstLoad);

  expect(await screen.findByText('로드중')).toBeDefined();
  expect(screen.getByLabelText('Model A 로드중').props.accessibilityState.disabled).toBe(true);
  expect(screen.getByLabelText('Model B 로드').props.accessibilityState.disabled).toBe(true);

  finishLoad?.();
  await waitFor(() => expect(onSelectedModelKeyChange).toHaveBeenCalledWith('model-a'));
});

test('disables unload while the loaded model is processing a request', async () => {
  (api.localModels as jest.Mock).mockResolvedValue({
    models: [{
      key: 'model-a', display_name: 'Model A', processing: true,
      loaded_instances: [{ id: 'instance-a' }],
    }],
  });
  render(<ModelManager token="token" onSelectedModelKeyChange={jest.fn()} />);

  fireEvent.press(await screen.findByLabelText('직접 모델 관리 상세 펼치기'));

  const processingButtons = await screen.findAllByText('처리중');
  expect(processingButtons.length).toBeGreaterThanOrEqual(2);
  expect(screen.getByLabelText('Model A 처리중').props.accessibilityState.disabled).toBe(true);
});
