export const CHARACTER_IDS = ['haru', 'nari'] as const;

export type CharacterId = (typeof CHARACTER_IDS)[number];

export const DEFAULT_CHARACTER_ID: CharacterId = 'haru';

export function isCharacterId(value: unknown): value is CharacterId {
  return typeof value === 'string' && CHARACTER_IDS.some((id) => id === value);
}
