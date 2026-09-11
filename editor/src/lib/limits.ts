/**
 * Limits the editor imposes on what it will display, and helpers for saying
 * so in a message.
 */

/**
 * Lines of a file the editor will show.
 *
 * Uploaded data files are the reason this exists: a CSV with fifty thousand
 * rows is a legitimate input to `#learn`, but loading it into CodeMirror
 * costs the browser a great deal and tells the user nothing they cannot see
 * from the first screenful. Beyond this many lines the editor shows a prefix
 * and says so.
 *
 * A file shown as a prefix is opened **read-only**, and the backend still
 * holds all of it: programs reading the file see every line.
 */
export const MAX_EDITOR_LINES = 1000;

/**
 * Physical lines in `text`, counted the way a file is iterated: a trailing
 * newline ends the last line rather than starting an empty one, so `"a\nb\n"`
 * and `"a\nb"` are both two lines. Matches `_line_count` in the runner's
 * `main.py`, so the count shown after an upload agrees with the one the
 * server reports when the file is opened.
 */
export function countLines(text: string): number {
  if (text === '') return 0;
  let lines = 1;
  for (let i = 0; i < text.length; i++) if (text[i] === '\n') lines++;
  return text.endsWith('\n') ? lines - 1 : lines;
}

/** Thousands separators, for line counts in prose. */
export function formatCount(n: number): string {
  return n.toLocaleString('en-US');
}

/** A file size a person can read: "820 bytes", "1.2 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}
