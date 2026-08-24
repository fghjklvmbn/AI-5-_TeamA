import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { api } from '../api';
import type { MemoryItem } from '../types';
import { MemoryScreen } from './MemoryScreen';

jest.mock('../api', () => ({
  api: {
    memories: jest.fn(),
    addMemory: jest.fn(),
    deleteMemory: jest.fn(),
  },
}));

const memories: MemoryItem[] = [
  {
    id: 'preference-1', memory_type: 'preference', content: '산책할 때 재즈를 듣는다',
    confidence: 0.9, importance: 0.8, created_at: '2026-08-24T00:00:00Z', updated_at: '2026-08-24T00:00:00Z',
  },
  {
    id: 'schedule-1', memory_type: 'schedule', content: '금요일에 병원 예약이 있다',
    confidence: 0.9, importance: 0.8, created_at: '2026-08-24T00:00:00Z', updated_at: '2026-08-24T00:00:00Z',
  },
];

beforeEach(() => {
  (api.memories as jest.Mock).mockImplementation(
    (_token: string, options: { query?: string; memoryType?: MemoryItem['memory_type'] }) => {
      const query = options.query?.trim().toLocaleLowerCase() ?? '';
      return Promise.resolve(memories.filter((item) => (
        (!options.memoryType || item.memory_type === options.memoryType)
        && (!query || item.content.toLocaleLowerCase().includes(query))
      )));
    },
  );
});

test('searches all memories and combines search with a selected category', async () => {
  render(<MemoryScreen token="token" />);
  expect(await screen.findByText('산책할 때 재즈를 듣는다')).toBeDefined();
  expect(screen.getByText('금요일에 병원 예약이 있다')).toBeDefined();

  fireEvent.changeText(screen.getByLabelText('기억 검색'), '재즈');
  await waitFor(() => expect(api.memories).toHaveBeenLastCalledWith(
    'token', expect.objectContaining({ query: '재즈', memoryType: undefined }),
  ));
  expect(await screen.findByText('산책할 때 재즈를 듣는다')).toBeDefined();

  fireEvent.press(screen.getByLabelText('일정 기억만 보기'));
  await waitFor(() => expect(api.memories).toHaveBeenLastCalledWith(
    'token', expect.objectContaining({ query: '재즈', memoryType: 'schedule' }),
  ));
  expect(await screen.findByText('조건에 맞는 기억이 없어요')).toBeDefined();
});
