import type { LocalModel, Persona } from '../types';

function normalizedModelIdentity(model: Pick<LocalModel, 'key' | 'display_name'>): string {
  return `${model.key} ${model.display_name || ''}`.toLowerCase().replace(/[\s._/-]+/g, '');
}

export function isDefaultConversationModel(
  model: Pick<LocalModel, 'key' | 'display_name'>,
): boolean {
  const identity = normalizedModelIdentity(model);
  return (identity.includes('qwen35') && identity.includes('4b'))
    || identity.includes('hyperclovax');
}

export function isHyperClovaConversationModel(
  model: Pick<LocalModel, 'key' | 'display_name'>,
): boolean {
  return normalizedModelIdentity(model).includes('hyperclovax');
}

export function conversationModelChoices(
  models: LocalModel[], persona: Persona,
): LocalModel[] {
  return persona === 'none' ? models : models.filter(isDefaultConversationModel);
}
