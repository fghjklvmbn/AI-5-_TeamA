import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import { api } from '../api';
import { PortraitScreen } from './PortraitScreen';

jest.mock('../api', () => ({
  api: {
    portrait: jest.fn(),
    generatePortrait: jest.fn(),
  },
}));

const completedPortrait = {
  status: 'complete' as const,
  title: '온기',
  summary: '따뜻한 대화를 소중히 여기는 모습이에요.',
  accuracy_percent: 88,
  analyzed_sessions: 6,
  analyzed_messages: 18,
  ready_for_generation: true,
  readiness_sessions: 6,
  readiness_turns: 11,
  readiness_characters: 751,
};

const belowThresholdPortrait = {
  ...completedPortrait,
  analyzed_sessions: 3,
  analyzed_messages: 3,
  ready_for_generation: false,
  readiness_sessions: 3,
  readiness_turns: 3,
  readiness_characters: 42,
};

test('a legacy completed portrait below the current threshold is blocked by fallback', async () => {
  (api.portrait as jest.Mock).mockResolvedValue(belowThresholdPortrait);
  const view = render(<PortraitScreen isActive persona="default" token="token" />);

  const confirm = await view.findByText('확인');
  expect(screen.getByText('완성된 자화상은 기준치 미만입니다.')).toBeDefined();
  expect(screen.getByText('정해진 기준을 넘지 않았기 때문에 재생성은 불가능합니다.')).toBeDefined();
  fireEvent.press(confirm);

  await waitFor(() => {
    expect(screen.queryByLabelText('완성된 자화상 확인')).toBeNull();
  });
  expect(screen.getByText('자화상 분석 기준을 충족하지 못했어요')).toBeDefined();
  expect(screen.getByText('3개 중 0개 충족')).toBeDefined();
  expect(screen.getByLabelText('세션 미충족, 현재 3개, 기준 6개')).toBeDefined();
  expect(screen.getByText('709자 더 필요해요')).toBeDefined();
  expect(screen.getByText('미충족 기준을 모두 채우면 재생성할 수 있어요.')).toBeDefined();
  expect(screen.queryByText('온기')).toBeNull();
});

test('leaving and returning to the portrait tab restores the threshold fallback', async () => {
  (api.portrait as jest.Mock).mockResolvedValue(belowThresholdPortrait);
  const view = render(<PortraitScreen isActive persona="default" token="token" />);
  fireEvent.press(await view.findByText('확인'));

  view.rerender(<PortraitScreen isActive={false} persona="default" token="token" />);
  view.rerender(<PortraitScreen isActive persona="default" token="token" />);

  expect(await screen.findByLabelText('완성된 자화상 확인')).toBeDefined();
});

test('a completed portrait meeting the current threshold is shown normally', async () => {
  (api.portrait as jest.Mock).mockResolvedValue(completedPortrait);
  render(<PortraitScreen isActive persona="default" token="token" />);

  expect(await screen.findByText('온기')).toBeDefined();
  expect(screen.queryByLabelText('완성된 자화상 확인')).toBeNull();
});
