import { recentVoiceRefreshMessages, splitSearchSources } from './messageContent';

test('keeps an answer without search sources unchanged', () => {
  expect(splitSearchSources('일반 답변입니다.')).toEqual({
    body: '일반 답변입니다.', sources: '', sourceCount: 0,
  });
});

test('selects at most ten completed answers in newest-first order for voice refresh', () => {
  const messages = Array.from({ length: 12 }, (_, index) => ({
    id: `message-${index + 1}`,
    user_text: `질문 ${index + 1}`,
    assistant_text: `답변 ${index + 1}`,
    created_at: `2026-08-25T00:00:${String(index).padStart(2, '0')}Z`,
  }));
  messages.push({
    id: 'pending-13', user_text: '진행 중', assistant_text: '진행 중',
    created_at: '2026-08-25T00:00:13Z',
  });

  expect(recentVoiceRefreshMessages(messages).map((message) => message.id)).toEqual([
    'message-12', 'message-11', 'message-10', 'message-9', 'message-8',
    'message-7', 'message-6', 'message-5', 'message-4', 'message-3',
  ]);
});

test('separates display-only search sources from the spoken answer body', () => {
  expect(splitSearchSources(
    '본문 답변입니다.\n\n### 검색 출처\n- [출처 1](https://example.com/1)\n- [출처 2](https://example.com/2)',
  )).toEqual({
    body: '본문 답변입니다.',
    sources: '- [출처 1](https://example.com/1)\n- [출처 2](https://example.com/2)',
    sourceCount: 2,
  });
});
