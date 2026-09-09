import { describe, expect, it } from 'vitest';
import { StringStream } from '@codemirror/language';

import { paspStreamParser } from './pasp';

/**
 * Runs the tokenizer over `text` and returns `[token, text]` pairs, skipping
 * whitespace. Lines are fed one at a time, as CodeMirror does, so that state
 * carried across lines (the `#python` block) is exercised.
 */
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
      // CodeMirror's StreamLanguage anchors `start` to the current position
      // before every token call, and modes rely on it: the legacy Python mode
      // takes its string delimiter from `stream.current()`. Without this the
      // harness, not the tokenizer, produces wrong tokens.
      stream.start = start;
      const token = paspStreamParser.token(stream, state);
      const value = line.slice(start, stream.pos);
      if (stream.pos === start) throw new Error(`tokenizer stalled at ${start} in ${line}`);
      if (value.trim() !== '') out.push([token, value]);
      if (++guard > 500) throw new Error('runaway tokenizer');
    }
  }
  return out;
}

/** Convenience: the token assigned to the first occurrence of `text`. */
function tokenOf(source: string, text: string): string | null | undefined {
  return tokenize(source).find(([, value]) => value === text)?.[0];
}

describe('comments', () => {
  it('treats % to end of line as a comment', () => {
    expect(tokenize('% hello world')).toEqual([['comment', '% hello world']]);
  });

  it('does not continue a comment onto the next line', () => {
    // dPASP's grammar has no block comments; the second line here is code and
    // must not be swallowed, or a syntax error would be hidden.
    const tokens = tokenize('%* looks like a block comment\nfoo.');
    expect(tokens[0]).toEqual(['comment', '%* looks like a block comment']);
    expect(tokens[1]).toEqual([null, 'foo']);
  });

  it('does not treat % inside a string as a comment', () => {
    expect(tokenOf('#learn @f, alg = "100%".', '"100%"')).toBe('string');
  });
});

describe('probabilistic annotations', () => {
  it('reads a probabilistic fact', () => {
    expect(tokenize('0.7::burglary.')).toEqual([
      ['number', '0.7'],
      ['operator', '::'],
      [null, 'burglary'],
      ['punctuation', '.']
    ]);
  });

  it('reads a credal fact', () => {
    const tokens = tokenize('[0.1, 0.3]::faulty.');
    expect(tokens.map(([t]) => t)).toEqual([
      'bracket',
      'number',
      'punctuation',
      'number',
      'bracket',
      'operator',
      null,
      'punctuation'
    ]);
  });

  it('marks a learnable annotation', () => {
    expect(tokenize('?::f.')).toEqual([
      ['operator', '?'],
      ['operator', '::'],
      [null, 'f'],
      ['punctuation', '.']
    ]);
  });
});

describe('rules', () => {
  it('reads the implication arrow as one operator', () => {
    expect(tokenOf('a :- b.', ':-')).toBe('operator');
  });

  it('highlights uppercase identifiers as variables', () => {
    expect(tokenOf('calls(X) :- neighbor(X).', 'X')).toBe('variable');
    expect(tokenOf('calls(X) :- neighbor(X).', 'calls')).toBe(null);
  });

  it('treats not as a keyword', () => {
    expect(tokenOf('a :- not b.', 'not')).toBe('keyword');
  });

  it('keeps the range operator separate from a float', () => {
    // `{0..9}` must read as 0, .., 9 — not as the float `0.` followed by `.9`.
    expect(tokenize('v({0..9}).').slice(1, 7)).toEqual([
      ['bracket', '('],
      ['bracket', '{'],
      ['number', '0'],
      ['operator', '..'],
      ['number', '9'],
      ['bracket', '}']
    ]);
  });
});

describe('directives', () => {
  it('marks #query as a directive', () => {
    expect(tokenOf('#query(alarm | burglary)', '#query')).toBe('macro');
  });

  it.each(['#semantics', '#learn', '#const', '#show', '#include'])('marks %s', (directive) => {
    expect(tokenOf(`${directive} x.`, directive)).toBe('macro');
  });

  it('marks #inf and #sup as constants, not directives', () => {
    expect(tokenOf('a :- X < #sup.', '#sup')).toBe('atom');
  });

  it('still marks an unknown directive as a directive', () => {
    expect(tokenOf('#nosuchthing.', '#nosuchthing')).toBe('macro');
  });
});

describe('neural rules and learning', () => {
  const rule = '?::digit(X, {0..9}) as @digit_net with optim = "Adam", lr = 0.001 :- input(X).';

  it('marks the external function', () => {
    expect(tokenOf(rule, '@digit_net')).toBe('function');
  });

  it('marks as/with as keywords', () => {
    expect(tokenOf(rule, 'as')).toBe('keyword');
    expect(tokenOf(rule, 'with')).toBe('keyword');
  });

  it('marks option names as properties only before =', () => {
    expect(tokenOf(rule, 'optim')).toBe('property');
    expect(tokenOf(rule, 'lr')).toBe('property');
    // The same word not followed by `=` is an ordinary predicate.
    expect(tokenOf('lr(3).', 'lr')).toBe(null);
  });

  it('marks the data-source builtins', () => {
    const data = 'input(x) ~ test(@mnist_test), train(@mnist_train).';
    expect(tokenOf(data, 'test')).toBe('builtin');
    expect(tokenOf(data, 'train')).toBe('builtin');
    expect(tokenOf(data, '~')).toBe('operator');
  });
});

describe('embedded python', () => {
  const program = ['#python', 'def f():', '  return "x"  # comment', '#end.', '0.5::a.'].join('\n');

  it('delegates the block body to the python mode', () => {
    const tokens = tokenize(program);
    expect(tokens[0]).toEqual(['macro', '#python']);
    // `def` and the string come from the Python mode, not the pasp tokenizer.
    expect(tokens.find(([, v]) => v === 'def')?.[0]).toBe('keyword');
    expect(tokens.find(([, v]) => v === '"x"')?.[0]).toBe('string');
    expect(tokens.find(([, v]) => v === '# comment')?.[0]).toBe('comment');
  });

  it('leaves the block and resumes pasp tokenizing after #end', () => {
    const tokens = tokenize(program);
    const end = tokens.findIndex(([, v]) => v.trim() === '#end');
    expect(tokens[end][0]).toBe('macro');
    // Back in pasp: the probability annotation is recognised again.
    expect(tokens.slice(end).find(([, v]) => v === '::')?.[0]).toBe('operator');
    expect(tokens.slice(end).find(([, v]) => v === '0.5')?.[0]).toBe('number');
  });
});

describe('robustness', () => {
  it('never stalls on unusual input', () => {
    const samples = [
      '',
      '   ',
      '&diff{x} = 3.',
      '"unterminated',
      '0x1f + 2 * 3 / 4 \\ 5 ^ 6.',
      '#script(python)\nx = 1\n#end.',
      ':~ a. [1@2]',
      'a; b; c :- d, not e, undef f.'
    ];
    for (const sample of samples) expect(() => tokenize(sample)).not.toThrow();
  });
});
