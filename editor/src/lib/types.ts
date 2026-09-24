/**
 * Shape of the payload returned by the dPASP runner's `/run` endpoint.
 * Mirrors the docstring in `backend/dPaspRunner/dpasp_api.py`.
 */

/**
 * A probability bound. JSON has no literals for non-finite numbers, so the
 * runner sends `"inf"`, `"-inf"` and `"nan"` as strings; these do occur, for
 * instance when a query is conditioned on an event of probability zero.
 */
export type Bound = number | 'inf' | '-inf' | 'nan';

export interface QueryResult {
  /** The query as dPASP printed it, e.g. `ℙ(alarm | burglary)`. */
  query: string;
  /** Raw bounds: `[lower, upper]` under credal, `[value]` under max-entropy. */
  values: Bound[];
  lower?: Bound;
  upper?: Bound;
  /**
   * 0-based test instance this answer belongs to, present only when the
   * program had more than one. A program with neural rules answers every
   * query once per row of its test data.
   */
  instance?: number;
}

export interface RunError {
  kind: 'parse' | 'runtime' | 'timeout' | 'internal';
  type: string;
  message: string;
  /** 1-based source position, when the parser could report one. */
  line?: number;
  column?: number;
}

export interface RunResult {
  ok: boolean;
  /** Logic semantics actually used. */
  sem: string;
  /** Probabilistic semantics actually used (a `#semantics` directive wins). */
  psem: string;
  /** True when bounds are lower/upper pairs rather than point values. */
  interval: boolean;
  /** True when the program carried a `#learn` directive. */
  learned: boolean;
  /**
   * Blocks of answers the run produced: 1 for an ordinary program, one per
   * row of test data for a program with neural rules.
   */
  instances?: number;
  /** How many of those blocks `queries` holds; smaller when truncated. */
  instances_shown?: number;
  elapsed_ms: number;
  queries: QueryResult[];
  /** Whatever the program itself printed. */
  output: string;
  error: RunError | null;
}

/** Formats a bound for display, matching the `pasp` CLI's six decimal places. */
export function formatBound(value: Bound | undefined): string {
  if (value === undefined || value === null) return '—';
  if (value === 'inf') return '∞';
  if (value === '-inf') return '−∞';
  if (value === 'nan') return 'undefined';
  return value.toFixed(6);
}

/** A bound's position in [0, 1], for the interval bars; non-finite -> clamped. */
export function boundFraction(value: Bound | undefined): number {
  if (typeof value !== 'number' || Number.isNaN(value)) return 0;
  return Math.min(1, Math.max(0, value));
}
