import { describe, expect, it } from 'vitest';
import { StringStream } from '@codemirror/language';

import { EXAMPLES, findExample } from './index';
import { paspStreamParser } from '$lib/lang/pasp';

describe('the example registry', () => {
  it('offers the programs the dialog advertises', () => {
    const ids = EXAMPLES.map((e) => e.id);
    expect(ids).toContain('earthquake');
    expect(ids).toContain('coloring');
    expect(ids).toContain('digitsum');
    expect(ids).toContain('argumentation');
    expect(ids).toContain('poisson');
  });

  it('has unique ids and filenames', () => {
    expect(new Set(EXAMPLES.map((e) => e.id)).size).toBe(EXAMPLES.length);
    expect(new Set(EXAMPLES.map((e) => e.filename)).size).toBe(EXAMPLES.length);
  });

  it('names every file with a .pasp extension', () => {
    for (const example of EXAMPLES) expect(example.filename).toMatch(/^[\w-]+\.pasp$/);
  });

  it('is looked up by id', () => {
    expect(findExample('earthquake')?.filename).toBe('earthquake.pasp');
    expect(findExample('nonexistent')).toBeUndefined();
  });
});

describe('the example programs', () => {
  it.each(EXAMPLES.map((e) => [e.id, e] as const))('%s loads its source', (_id, example) => {
    // Imported with `?raw`; an empty string would mean the import resolved to
    // nothing, which type-checking cannot catch.
    expect(example.code.length).toBeGreaterThan(50);
    expect(example.code).toContain('#query');
  });

  it.each(EXAMPLES.map((e) => [e.id, e] as const))('%s ends with a newline', (_id, example) => {
    // Not housekeeping. dPASP’s parser needs the newline to close a `%`
    // comment, so a file whose last line is
    //
    //     #query joint. % P(joint) = 0.001
    //
    // with no trailing newline fails to parse at all:
    //
    //     UnexpectedCharacters: No terminal matches '%' ... at line 28 col 15
    //
    // Measured against real dPASP with the poisson example, which arrived
    // without one. The run path happens to paper over it — `submit` sends
    // `content + '\n'` — but the stored source should be correct on its own,
    // since it is also what a download hands the user.
    expect(example.code.endsWith('\n')).toBe(true);
  });

  it.each(EXAMPLES.map((e) => [e.id, e] as const))(
    '%s carries a description',
    (_id, example) => {
      expect(example.description.trim().length).toBeGreaterThan(20);
      expect(example.label.trim()).not.toBe('');
    }
  );

  it('warns about exactly the programs that need more than a plain run', () => {
    // digitsum trains on MNIST, so a plain run reports a timeout; learning
    // reads its CSV over the network at parse time. The dialog says so up
    // front rather than letting either look broken. Everything else runs as
    // is, and a note on those would be noise.
    const noted = EXAMPLES.filter((e) => e.note !== undefined).map((e) => e.id);
    expect(noted.sort()).toEqual(['digitsum', 'learning']);
    for (const id of noted) expect(findExample(id)?.note?.trim().length).toBeGreaterThan(20);
  });
});

/** Tokenizes with the pasp mode, returning the tokens it produced. */
function tokenize(text: string): Array<[string | null, string]> {
  const state = paspStreamParser.startState!(2);
  const out: Array<[string | null, string]> = [];

  for (const line of text.split('\n')) {
    const stream = new StringStream(line, 2, 2);
    if (line.length === 0) {
      paspStreamParser.blankLine?.(state, 2);
      continue;
    }
    let guard = 0;
    while (!stream.eol()) {
      const start = stream.pos;
      stream.start = start;
      const token = paspStreamParser.token(stream, state);
      if (stream.pos === start) throw new Error(`tokenizer stalled in: ${line}`);
      const value = line.slice(start, stream.pos);
      if (value.trim() !== '') out.push([token, value]);
      if (++guard > 5000) throw new Error('runaway tokenizer');
    }
  }
  return out;
}

describe('the examples highlight cleanly', () => {
  it.each(EXAMPLES.map((e) => [e.id, e] as const))('%s tokenizes', (_id, example) => {
    const tokens = tokenize(example.code);

    expect(tokens.length).toBeGreaterThan(20);
    // The mode has no error token, but a stall or an unstyled `#query` would
    // mean the example uses syntax the highlighter does not know.
    expect(tokens.some(([token]) => token === 'error')).toBe(false);
    expect(tokens.some(([token, value]) => token === 'macro' && value.startsWith('#query'))).toBe(
      true
    );
  });

  it('highlights the credal facts in the prisoners program', () => {
    const tokens = tokenize(findExample('prisoners')!.code);
    // `[0.475, 0.525]::a` — the bracketed interval and the `::` annotation.
    expect(tokens.some(([t, v]) => t === 'number' && v === '0.475')).toBe(true);
    expect(tokens.some(([t, v]) => t === 'operator' && v === '::')).toBe(true);
  });

  it('delegates the poisson python block to the python mode', () => {
    const tokens = tokenize(findExample('poisson')!.code);
    expect(tokens.find(([, v]) => v === '#python')?.[0]).toBe('macro');
    // `class` and `def` come from the embedded Python mode — this example is
    // the short demonstration of the torch integration.
    expect(tokens.some(([t, v]) => t === 'keyword' && v === 'class')).toBe(true);
    // Back in pasp afterwards: the neural AD’s model and the data function.
    expect(tokens.some(([t, v]) => t === 'function' && v === '@Poisson')).toBe(true);
    expect(tokens.some(([t, v]) => t === 'function' && v === '@get_data')).toBe(true);
  });

  it('highlights the two separate semantics directives in argumentation', () => {
    // The program declares the logic and probabilistic halves in one
    // directive each, rather than the combined `#semantics a, b.` form.
    const tokens = tokenize(findExample('argumentation')!.code);
    const macros = tokens.filter(([t]) => t === 'macro').map(([, v]) => v);
    expect(macros.filter((m) => m === '#semantics').length).toBe(2);
  });

  it('delegates the digitsum python block to the python mode', () => {
    const tokens = tokenize(findExample('digitsum')!.code);
    expect(tokens.find(([, v]) => v === '#python')?.[0]).toBe('macro');
    // `class` and `def` come from the embedded Python mode.
    expect(tokens.some(([t, v]) => t === 'keyword' && v === 'class')).toBe(true);
    expect(tokens.some(([t, v]) => t === 'keyword' && v === 'def')).toBe(true);
    // Back in pasp afterwards: the neural rule's external function.
    expect(tokens.some(([t, v]) => t === 'function' && v === '@digit_net')).toBe(true);
  });

  it('highlights the undef queries in the colouring program', () => {
    const tokens = tokenize(findExample('coloring')!.code);
    expect(tokens.some(([t, v]) => t === 'keyword' && v === 'undef')).toBe(true);
    expect(tokens.some(([t, v]) => t === 'macro' && v === '#semantics')).toBe(true);
  });
});
