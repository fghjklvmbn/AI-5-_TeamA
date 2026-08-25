export type DisplayMessageContent = {
  body: string;
  sources: string;
  sourceCount: number;
};

const searchSourcesHeading = /(?:^|\n)###\s+검색 출처\s*(?:\n|$)/;

export function splitSearchSources(source: string): DisplayMessageContent {
  const match = searchSourcesHeading.exec(source);
  if (!match || match.index === undefined) {
    return { body: source, sources: '', sourceCount: 0 };
  }
  const sources = source.slice(match.index + match[0].length).trim();
  return {
    body: source.slice(0, match.index).trimEnd(),
    sources,
    sourceCount: sources.match(/^\s*[-+*]\s+/gm)?.length ?? 0,
  };
}

export function recentVoiceRefreshMessages(messages: Message[], limit = 10): Message[] {
  return messages
    .filter((message) => (
      !message.id.startsWith('pending-') && !!message.assistant_text.trim()
    ))
    .slice(-Math.max(0, limit))
    .reverse();
}
import type { Message } from '../types';
