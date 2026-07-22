import React from 'react';
import { Linking, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';

import { useTheme, type ThemeColors } from '../theme';

type MarkdownBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'heading'; level: number; text: string }
  | { type: 'unordered-list'; text: string }
  | { type: 'ordered-list'; number: string; text: string }
  | { type: 'quote'; text: string }
  | { type: 'code'; language: string; text: string }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'rule' };

const headingPattern = /^(#{1,6})\s+(.+)$/;
const unorderedPattern = /^\s*[-+*]\s+(.+)$/;
const orderedPattern = /^\s*(\d+)[.)]\s+(.+)$/;
const quotePattern = /^\s*>\s?(.*)$/;
const rulePattern = /^\s*(?:-{3,}|_{3,}|\*{3,})\s*$/;

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
}

function isTableDelimiter(line: string): boolean {
  const cells = splitTableRow(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function startsBlock(lines: string[], index: number): boolean {
  const line = lines[index] ?? '';
  return line.startsWith('```')
    || headingPattern.test(line)
    || unorderedPattern.test(line)
    || orderedPattern.test(line)
    || quotePattern.test(line)
    || rulePattern.test(line)
    || (line.includes('|') && isTableDelimiter(lines[index + 1] ?? ''));
}

export function parseMarkdownBlocks(source: string): MarkdownBlock[] {
  const lines = source.replace(/\r\n?/g, '\n').split('\n');
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? '';
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith('```')) {
      const language = line.slice(3).trim();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !(lines[index] ?? '').startsWith('```')) {
        code.push(lines[index] ?? '');
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ type: 'code', language, text: code.join('\n') });
      continue;
    }

    const heading = line.match(headingPattern);
    if (heading) {
      blocks.push({
        type: 'heading',
        level: (heading[1] ?? '#').length,
        text: (heading[2] ?? '').trim(),
      });
      index += 1;
      continue;
    }

    if (line.includes('|') && isTableDelimiter(lines[index + 1] ?? '')) {
      const headers = splitTableRow(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && (lines[index] ?? '').includes('|') && (lines[index] ?? '').trim()) {
        rows.push(splitTableRow(lines[index] ?? ''));
        index += 1;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    const unordered = line.match(unorderedPattern);
    if (unordered) {
      blocks.push({ type: 'unordered-list', text: (unordered[1] ?? '').trim() });
      index += 1;
      continue;
    }

    const ordered = line.match(orderedPattern);
    if (ordered) {
      blocks.push({
        type: 'ordered-list',
        number: ordered[1] ?? '',
        text: (ordered[2] ?? '').trim(),
      });
      index += 1;
      continue;
    }

    const quote = line.match(quotePattern);
    if (quote) {
      const quoteLines: string[] = [quote[1] ?? ''];
      index += 1;
      while (index < lines.length) {
        const next = (lines[index] ?? '').match(quotePattern);
        if (!next) break;
        quoteLines.push(next[1] ?? '');
        index += 1;
      }
      blocks.push({ type: 'quote', text: quoteLines.join('\n').trim() });
      continue;
    }

    if (rulePattern.test(line)) {
      blocks.push({ type: 'rule' });
      index += 1;
      continue;
    }

    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && (lines[index] ?? '').trim() && !startsBlock(lines, index)) {
      paragraph.push((lines[index] ?? '').trim());
      index += 1;
    }
    blocks.push({ type: 'paragraph', text: paragraph.join('\n') });
  }

  return blocks;
}

const inlinePattern = /(\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^\s)]+\)|\*[^*\n]+\*|_[^_\n]+_)/g;

function renderInline(source: string, styles: ReturnType<typeof createStyles>): React.ReactNode[] {
  const result: React.ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  for (const match of source.matchAll(inlinePattern)) {
    const start = match.index ?? 0;
    if (start > cursor) result.push(source.slice(cursor, start));
    const token = match[0] ?? '';
    const tokenKey = `inline-${key}`;

    if ((token.startsWith('**') && token.endsWith('**')) || (token.startsWith('__') && token.endsWith('__'))) {
      result.push(<Text key={tokenKey} style={styles.strong}>{token.slice(2, -2)}</Text>);
    } else if (token.startsWith('~~') && token.endsWith('~~')) {
      result.push(<Text key={tokenKey} style={styles.strike}>{token.slice(2, -2)}</Text>);
    } else if (token.startsWith('`') && token.endsWith('`')) {
      result.push(<Text key={tokenKey} style={styles.inlineCode}>{token.slice(1, -1)}</Text>);
    } else if (token.startsWith('[')) {
      const link = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (link) {
        result.push(
          <Text
            accessibilityRole="link"
            key={tokenKey}
            onPress={() => { void Linking.openURL(link[2] ?? '').catch(() => undefined); }}
            style={styles.link}
          >
            {link[1] ?? ''}
          </Text>,
        );
      } else result.push(token);
    } else {
      result.push(<Text key={tokenKey} style={styles.emphasis}>{token.slice(1, -1)}</Text>);
    }
    cursor = start + token.length;
    key += 1;
  }

  if (cursor < source.length) result.push(source.slice(cursor));
  return result;
}

export function MarkdownMessage({ children }: { children: string }) {
  const { colors } = useTheme();
  const styles = createStyles(colors);
  const blocks = parseMarkdownBlocks(children);

  return (
    <View style={styles.body}>
      {blocks.map((block, index) => {
        const key = `block-${index}`;
        if (block.type === 'heading') {
          const headingStyle = block.level <= 1
            ? styles.heading1
            : block.level === 2 ? styles.heading2 : styles.heading3;
          return <Text key={key} selectable style={headingStyle}>{renderInline(block.text, styles)}</Text>;
        }
        if (block.type === 'unordered-list' || block.type === 'ordered-list') {
          return (
            <View key={key} style={styles.listRow}>
              <Text style={styles.listMarker}>{block.type === 'ordered-list' ? `${block.number}.` : '•'}</Text>
              <Text selectable style={styles.listText}>{renderInline(block.text, styles)}</Text>
            </View>
          );
        }
        if (block.type === 'quote') {
          return <Text key={key} selectable style={styles.quote}>{renderInline(block.text, styles)}</Text>;
        }
        if (block.type === 'code') {
          return (
            <View key={key} style={styles.codeContainer}>
              {!!block.language && <Text style={styles.codeLanguage}>{block.language}</Text>}
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <Text selectable style={styles.codeBlock}>{block.text}</Text>
              </ScrollView>
            </View>
          );
        }
        if (block.type === 'table') {
          const width = Math.max(300, block.headers.length * 120);
          return (
            <ScrollView horizontal key={key} showsHorizontalScrollIndicator={false} style={styles.tableScroll}>
              <View style={[styles.table, { minWidth: width }]}>
                <View style={[styles.tableRow, styles.tableHeaderRow]}>
                  {block.headers.map((cell, cellIndex) => (
                    <Text key={`header-${cellIndex}`} style={[styles.tableCell, styles.tableHeaderCell]}>
                      {renderInline(cell, styles)}
                    </Text>
                  ))}
                </View>
                {block.rows.map((row, rowIndex) => (
                  <View key={`row-${rowIndex}`} style={styles.tableRow}>
                    {block.headers.map((_, cellIndex) => (
                      <Text key={`cell-${cellIndex}`} style={styles.tableCell}>
                        {renderInline(row[cellIndex] ?? '', styles)}
                      </Text>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          );
        }
        if (block.type === 'rule') return <View key={key} style={styles.rule} />;
        return <Text key={key} selectable style={styles.paragraph}>{renderInline(block.text, styles)}</Text>;
      })}
    </View>
  );
}

const createStyles = (colors: ThemeColors) => StyleSheet.create({
  body: { width: '100%' },
  paragraph: { color: colors.ink, fontSize: 15, lineHeight: 23, marginBottom: 8 },
  heading1: { color: colors.ink, fontSize: 21, lineHeight: 28, fontWeight: '900', marginBottom: 10 },
  heading2: { color: colors.ink, fontSize: 18, lineHeight: 25, fontWeight: '900', marginBottom: 9 },
  heading3: { color: colors.ink, fontSize: 16, lineHeight: 23, fontWeight: '900', marginBottom: 8 },
  strong: { color: colors.ink, fontWeight: '900' },
  emphasis: { color: colors.ink, fontStyle: 'italic' },
  strike: { color: colors.muted, textDecorationLine: 'line-through' },
  inlineCode: { color: colors.primaryDark, backgroundColor: colors.primarySoft, fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }), fontSize: 13 },
  link: { color: colors.primaryDark, fontWeight: '800', textDecorationLine: 'underline' },
  listRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 6, paddingRight: 4 },
  listMarker: { width: 24, color: colors.primaryDark, fontSize: 14, lineHeight: 22, fontWeight: '900', textAlign: 'right', marginRight: 8 },
  listText: { flex: 1, color: colors.ink, fontSize: 15, lineHeight: 22 },
  quote: { color: colors.muted, fontSize: 14, lineHeight: 22, borderLeftWidth: 3, borderLeftColor: colors.primary, backgroundColor: colors.primarySoft, paddingHorizontal: 12, paddingVertical: 9, marginBottom: 9 },
  codeContainer: { maxWidth: '100%', borderRadius: 12, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.subtle, padding: 10, marginBottom: 9 },
  codeLanguage: { color: colors.muted, fontSize: 9, fontWeight: '800', textTransform: 'uppercase', marginBottom: 6 },
  codeBlock: { color: colors.ink, fontFamily: Platform.select({ ios: 'Menlo', default: 'monospace' }), fontSize: 12, lineHeight: 19 },
  tableScroll: { maxWidth: '100%', marginBottom: 9 },
  table: { borderWidth: 1, borderColor: colors.border, borderRadius: 10, overflow: 'hidden' },
  tableRow: { flexDirection: 'row', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  tableHeaderRow: { backgroundColor: colors.primarySoft },
  tableCell: { flex: 1, minWidth: 100, color: colors.ink, fontSize: 12, lineHeight: 18, paddingHorizontal: 9, paddingVertical: 8, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: colors.border },
  tableHeaderCell: { color: colors.primaryDark, fontWeight: '900' },
  rule: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: 10 },
});
