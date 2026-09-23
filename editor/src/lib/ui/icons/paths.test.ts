import { describe, expect, it } from 'vitest';

import { DOWNLOAD, FILE, PLAY, TABLE, UPLOAD, fileGlyph } from './paths';

describe('fileGlyph', () => {
  it('gives dPASP programs the document glyph', () => {
    for (const name of ['earthquake.pasp', 'learning.plp', 'graph.lp', 'query.pl']) {
      const glyph = fileGlyph(name);
      expect(glyph.d, name).toBe(FILE);
      expect(glyph.solid, name).toBe(true);
      expect(glyph.label, name).toBe('dPASP program');
    }
  });

  it('gives data files the table glyph', () => {
    for (const name of ['train.csv', 'observations.tsv']) {
      const glyph = fileGlyph(name);
      expect(glyph.d, name).toBe(TABLE);
      expect(glyph.solid, name).toBe(false);
      expect(glyph.label, name).toBe('data file');
    }
  });

  it('matches the extension whatever its case', () => {
    // Uploads come from the user's machine, where `DATA.CSV` is ordinary.
    expect(fileGlyph('DATA.CSV').d).toBe(TABLE);
    expect(fileGlyph('Model.PASP').d).toBe(FILE);
  });

  it('falls back to the plain document rather than guessing', () => {
    for (const name of ['notes.txt', 'README', 'archive.tar.gz', '']) {
      const glyph = fileGlyph(name);
      expect(glyph.d, name).toBe(FILE);
      expect(glyph.label, name).toBe('file');
    }
  });

  it('does not match an extension that merely appears in the name', () => {
    // `.csv` in the middle is not a CSV; `endsWith` is the whole rule.
    expect(fileGlyph('csv-notes.pasp').d).toBe(FILE);
    expect(fileGlyph('my.csv.pasp').label).toBe('dPASP program');
  });

  it('keeps the two file glyphs visually distinct', () => {
    // The point of the pair is that a program and its data differ at a
    // glance: same path for both would pass every test above.
    expect(TABLE).not.toBe(FILE);
    expect(fileGlyph('a.pasp').solid).not.toBe(fileGlyph('a.csv').solid);
  });

  it('every path is non-empty SVG path data', () => {
    for (const d of [FILE, TABLE, UPLOAD, DOWNLOAD, PLAY]) {
      expect(d).toMatch(/^M[\d.\s]/);
      expect(d.length).toBeGreaterThan(10);
    }
  });
});
