import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { ConversationModeTabs } from './ConversationModeTabs';

test('uses the character, chat, and hybrid labels', () => {
  const onChange = jest.fn();
  render(<ConversationModeTabs onChange={onChange} value="chat" />);

  expect(screen.getByText('캐릭터')).toBeDefined();
  expect(screen.getByText('채팅')).toBeDefined();
  expect(screen.getByText('하이브리드')).toBeDefined();

  fireEvent.press(screen.getByLabelText('캐릭터 대화 모드'));
  expect(onChange).toHaveBeenCalledWith('live');
});
