import { describe, it, expect } from 'vitest';
import { MAX_EDITOR_LINES, countLines, formatBytes, formatCount } from './limits';

describe('countLines', () => {
  it('counts a trailing newline as ending the last line, not starting one', () => {
    // Must agree with `_line_count` in the runner's main.py: the count shown
    // after an upload and the one shown when the file is opened come from
    // different sides of the wire and have to match.
    expect(countLines('a\nb\n')).toBe(2);
    expect(countLines('a\nb')).toBe(2);
  });

  it('counts the empty file as no lines', () => {
    expect(countLines('')).toBe(0);
  });

  it('counts a lone newline as one line', () => {
    expect(countLines('\n')).toBe(1);
  });

  it('agrees with the limit on a file just over it', () => {
    const csv = Array.from({ length: MAX_EDITOR_LINES + 1 }, (_, i) => `row${i}`).join('\n') + '\n';
    expect(countLines(csv)).toBe(MAX_EDITOR_LINES + 1);
    expect(countLines(csv) > MAX_EDITOR_LINES).toBe(true);
  });

  it('does not flag a file exactly at the limit', () => {
    const csv = Array.from({ length: MAX_EDITOR_LINES }, (_, i) => `row${i}`).join('\n') + '\n';
    expect(countLines(csv) > MAX_EDITOR_LINES).toBe(false);
  });
});

describe('formatBytes', () => {
  it('leaves small files in bytes', () => {
    expect(formatBytes(0)).toBe('0 bytes');
    expect(formatBytes(820)).toBe('820 bytes');
    expect(formatBytes(1023)).toBe('1023 bytes');
  });

  it('switches to larger units with one decimal until they get wide', () => {
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1536)).toBe('1.5 KB');
    expect(formatBytes(20 * 1024)).toBe('20 KB');
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB');
    expect(formatBytes(5 * 1024 * 1024 * 1024)).toBe('5.0 GB');
  });
});

describe('formatCount', () => {
  it('groups thousands, since these numbers are read in a sentence', () => {
    expect(formatCount(5000)).toBe('5,000');
    expect(formatCount(MAX_EDITOR_LINES)).toBe('1,000');
    expect(formatCount(42)).toBe('42');
  });
});
