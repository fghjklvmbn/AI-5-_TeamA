import { splitSearchSources } from './messageContent';

test('keeps an answer without search sources unchanged', () => {
  expect(splitSearchSources('일반 답변입니다.')).toEqual({
    body: '일반 답변입니다.', sources: '', sourceCount: 0,
  });
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
