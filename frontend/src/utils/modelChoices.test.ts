import type { LocalModel } from '../types';
import { conversationModelChoices, isHyperClovaConversationModel } from './modelChoices';

const models: LocalModel[] = [
  { key: 'hyperclovax-seed-text-instruct-1.5b', display_name: 'HyperCLOVA X' },
  { key: 'qwen3.5-4b', display_name: 'Qwen 3.5 4B' },
  { key: 'downloaded-model-2b', display_name: 'Downloaded Model' },
];

test('limits the default persona to HyperCLOVA X and Qwen', () => {
  expect(conversationModelChoices(models, 'default').map((model) => model.key)).toEqual([
    'hyperclovax-seed-text-instruct-1.5b',
    'qwen3.5-4b',
  ]);
});

test('keeps downloaded models available when persona is none', () => {
  expect(conversationModelChoices(models, 'none')).toEqual(models);
});

test('identifies HyperCLOVA X as the default fallback model', () => {
  expect(models.find(isHyperClovaConversationModel)?.key).toBe(
    'hyperclovax-seed-text-instruct-1.5b',
  );
});
