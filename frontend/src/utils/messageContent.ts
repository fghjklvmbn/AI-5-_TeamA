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
