/**
 * CodeMirror 6 language support for dPASP (.pasp / .plp / .lp) programs.
 *
 * Ported from the Pygments lexer in `pygments_pasp/pygments_pasp/pasp.py`
 * (itself adapted from Roland Kaminski's clingo lexer), extended with the
 * dPASP-specific constructs: probabilistic/credal/learnable annotations,
 * annotated disjunctions, neural rules and the `#python ... #end.` blocks.
 *
 * Embedded Python inside `#python`/`#script(python)` blocks is delegated to
 * the legacy CodeMirror Python mode, mirroring the Pygments lexer's
 * `using(PythonLexer)`.
 */

import {
  LanguageSupport,
  StreamLanguage,
  type StreamParser,
} from '@codemirror/language';
import type { CompletionContext, CompletionResult } from '@codemirror/autocomplete';
import { python as legacyPython } from '@codemirror/legacy-modes/mode/python';
import { tags as t } from '@lezer/highlight';

/* ------------------------------------------------------------------ *
 * Token names -> highlight tags.
 *
 * Legacy CodeMirror-5 style names are used so that tokens produced by the
 * embedded Python mode are mapped as well. `macro` and `function` are the
 * two names only the pasp tokenizer emits.
 * ------------------------------------------------------------------ */
// Tags are chosen so that neighbouring categories get distinct colours under
// One Dark, which is the theme the playground ships: `#`-directives take the
// keyword colour, the word operators (`not`, `as`, `with`) the operator
// colour, and variables the plain name colour. Mapping directives to
// `macroName` instead would give them the same colour as variables.
const tokenTable = {
  comment: t.comment,
  number: t.number,
  string: t.string,
  'string-2': t.special(t.string),
  keyword: t.operatorKeyword,
  macro: t.keyword,
  atom: t.atom,
  variable: t.variableName,
  'variable-2': t.special(t.variableName),
  'variable-3': t.typeName,
  type: t.typeName,
  def: t.definition(t.name),
  builtin: t.standard(t.name),
  function: t.function(t.variableName),
  operator: t.operator,
  punctuation: t.punctuation,
  bracket: t.bracket,
  property: t.propertyName,
  meta: t.meta,
  tag: t.tagName,
  qualifier: t.modifier,
  error: t.invalid,
};

/* ------------------------------------------------------------------ *
 * Keyword sets
 * ------------------------------------------------------------------ */

/** Solver/meta directives. All are spelled with a leading `#`. */
const DIRECTIVES = [
  'query',
  'learn',
  'semantics',
  'const',
  'show',
  'include',
  'python',
  'script',
  'end',
  'count',
  'sum',
  'min',
  'max',
  'minimize',
  'maximize',
  'defined',
  'external',
  'heuristic',
  'project',
  'program',
  'theory',
  'edge',
];

/** `#`-prefixed constants. */
const CONSTANTS = ['inf', 'sup', 'true', 'false'];

/** Bare word keywords. */
const KEYWORDS = ['not', 'undef', 'as', 'in', 'on', 'at', 'with'];

/** dPASP data-source builtins, used in `input(x) ~ test(@f), train(@g).` */
const BUILTINS = ['test', 'train'];

/**
 * Option names accepted after `with` in neural rules and in `#learn`.
 * Highlighted as properties only when directly followed by `=`.
 */
const OPTIONS = [
  'optim',
  'lr',
  'niters',
  'alg',
  'batch',
  'momentum',
  'weight_decay',
  'wd',
  'eps',
  'l2',
  'psemantics',
  'semantics',
  'display',
  'seed',
];

const DIRECTIVE_RE = new RegExp('^#(' + DIRECTIVES.join('|') + ')\\b');
const CONSTANT_RE = new RegExp('^#(' + CONSTANTS.join('|') + ')\\b');
const KEYWORD_RE = new RegExp('^(' + KEYWORDS.join('|') + ')\\b');
const BUILTIN_RE = new RegExp('^(' + BUILTINS.join('|') + ')\\b(?=\\s*\\()');
const OPTION_RE = new RegExp('^(' + OPTIONS.join('|') + ')\\b(?=\\s*=(?!=))');

/* ------------------------------------------------------------------ *
 * Tokenizer state
 * ------------------------------------------------------------------ */
interface PaspState {
  /** Set while inside a `#python`/`#script(python)` block. */
  inPython: boolean;
  /** State of the delegated Python mode, if any. */
  pyState: unknown;
}

export const paspStreamParser: StreamParser<PaspState> = {
  name: 'pasp',

  startState(): PaspState {
    return { inPython: false, pyState: null };
  },

  token(stream, state): string | null {
    // ---- inside an embedded Python block -----------------------------
    if (state.inPython) {
      // `#end.` closes the block. Only recognised at the start of a line so
      // that a `#end` inside Python source (e.g. a comment) is left alone.
      if (stream.sol() && stream.match(/^[ \t]*#end\b/)) {
        state.inPython = false;
        state.pyState = null;
        return 'macro';
      }
      // The Python mode handles its own whitespace and tracks indentation
      // from the start of the line, so the stream is handed over untouched.
      return legacyPython.token(stream, state.pyState as any) ?? null;
    }

    if (stream.eatSpace()) return null;

    // ---- comments ----------------------------------------------------
    // dPASP has only line comments: its grammar defines
    // `COMMENT: "%" /[^\n]*/ NEWLINE` and nothing else. The clingo-derived
    // Pygments lexer also highlights `%* ... *%` block comments, but the
    // dPASP parser rejects their continuation lines, so highlighting them as
    // comments would hide a syntax error rather than reveal it.
    if (stream.match(/^%.*/)) return 'comment';

    // ---- strings -----------------------------------------------------
    if (stream.match(/^"(\\.|[^\\"])*"/)) return 'string';
    if (stream.match(/^"(\\.|[^\\"])*$/)) return 'string'; // unterminated
    // `#include <file>`
    if (stream.match(/^<(\\.|[^\\>])*>/)) return 'string';

    // ---- numbers -----------------------------------------------------
    if (stream.match(/^0[xX][0-9a-fA-F]+/)) return 'number';
    // A float is only a float when the dot is followed by a digit, so that
    // the `..` range operator in `{0..9}` is not swallowed.
    if (stream.match(/^\d+\.\d+([eE][-+]?\d+)?/)) return 'number';
    if (stream.match(/^\d+/)) return 'number';

    // ---- directives and `#`-constants --------------------------------
    if (stream.match(CONSTANT_RE)) return 'atom';
    if (stream.match(DIRECTIVE_RE)) {
      const text = stream.current();
      if (text === '#python') {
        state.inPython = true;
        state.pyState = legacyPython.startState ? legacyPython.startState(2) : {};
      } else if (text === '#script') {
        // `#script(python) ... #end.` — the language name is consumed below
        // as ordinary text; only Python bodies are delegated.
        const rest = stream.string.slice(stream.pos);
        if (/^\s*\(\s*python\s*\)/.test(rest)) {
          state.inPython = true;
          state.pyState = legacyPython.startState ? legacyPython.startState(2) : {};
        }
      }
      return 'macro';
    }
    // Unknown `#foo` directive: still flag it as a macro rather than an error,
    // since clingo keeps growing its directive set.
    if (stream.match(/^#[a-z_][a-zA-Z0-9_]*/)) return 'macro';

    // ---- external python functions: @net, @mnist_labels_train --------
    if (stream.match(/^@[a-zA-Z_][a-zA-Z0-9_]*/)) return 'function';

    // ---- theory atoms: &diff, &sum ------------------------------------
    if (stream.match(/^&[_]*[a-z][a-zA-Z0-9_]*/)) return 'keyword';

    // ---- learning option names, before generic identifiers -----------
    if (stream.match(OPTION_RE)) return 'property';

    // ---- data-source builtins ----------------------------------------
    if (stream.match(BUILTIN_RE)) return 'builtin';

    // ---- bare keywords ------------------------------------------------
    if (stream.match(KEYWORD_RE)) return 'keyword';

    // ---- identifiers --------------------------------------------------
    // Variables start with an uppercase letter (or are the anonymous `_`).
    if (stream.match(/^[_']*[A-Z][0-9a-zA-Z'_]*/)) return 'variable';
    if (stream.match(/^_(?![0-9a-zA-Z'_])/)) return 'variable';
    // Predicates/constants start lowercase; left unstyled, as in the
    // Pygments lexer, so that rule bodies stay readable.
    if (stream.match(/^[_']*[a-z][0-9a-zA-Z'_]*/)) return null;

    // ---- operators ----------------------------------------------------
    // Longest match first: `:~` and `:-` before `:`, `::` before `:`,
    // `..` before `.`, `?::` handled by `?` + `::`.
    if (stream.match('::')) return 'operator';
    if (stream.match(':-')) return 'operator';
    if (stream.match(':~')) return 'operator';
    if (stream.match('..')) return 'operator';
    if (stream.match(/^(!=|<=|>=|==|<|>|=)/)) return 'operator';
    if (stream.match(/^(\+|-|\*\*|\*|\/|\\|\^|~|\||\?)/)) return 'operator';

    // ---- punctuation ---------------------------------------------------
    if (stream.match(/^[()\[\]{}]/)) return 'bracket';
    if (stream.match(/^[.,;:]/)) return 'punctuation';

    stream.next();
    return null;
  },

  blankLine(state) {
    if (state.inPython && legacyPython.blankLine) {
      legacyPython.blankLine(state.pyState as any, 2);
    }
  },

  copyState(state): PaspState {
    return {
      inPython: state.inPython,
      pyState:
        state.inPython && state.pyState && legacyPython.copyState
          ? legacyPython.copyState(state.pyState as any)
          : state.pyState,
    };
  },

  languageData: {
    commentTokens: { line: '%' },
    closeBrackets: { brackets: ['(', '[', '{', '"'] },
  },

  tokenTable,
};

export const paspLanguage = StreamLanguage.define(paspStreamParser);

/* ------------------------------------------------------------------ *
 * Completion of directives, keywords and learning options
 * ------------------------------------------------------------------ */
const completions = [
  ...DIRECTIVES.map((d) => ({
    label: '#' + d,
    type: 'keyword' as const,
    detail: 'directive',
  })),
  ...CONSTANTS.map((c) => ({
    label: '#' + c,
    type: 'constant' as const,
  })),
  ...KEYWORDS.map((k) => ({ label: k, type: 'keyword' as const })),
  ...BUILTINS.map((b) => ({
    label: b,
    type: 'function' as const,
    detail: 'data source',
  })),
  ...OPTIONS.map((o) => ({
    label: o,
    type: 'property' as const,
    detail: 'option',
  })),
];

function paspCompletion(context: CompletionContext): CompletionResult | null {
  const word = context.matchBefore(/#?[\w_]*/);
  if (!word || (word.from === word.to && !context.explicit)) return null;
  return { from: word.from, options: completions, validFor: /^#?[\w_]*$/ };
}

/** Full language support: highlighting plus directive completion. */
export function pasp(): LanguageSupport {
  return new LanguageSupport(paspLanguage, [
    paspLanguage.data.of({ autocomplete: paspCompletion }),
  ]);
}
