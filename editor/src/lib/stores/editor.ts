import { writable } from 'svelte/store';
import type { RunResult } from '$lib/types';

export const currentFileContent = writable<string>('');
export const currentFile = writable<string>('');

/** How much of the open file the buffer above actually holds. */
export interface Truncation {
  /** Lines the file has on the server. */
  totalLines: number;
  /** Lines the editor is showing, always the first ones. */
  shownLines: number;
  /** Size of the whole file on the server. */
  bytes: number;
}

/**
 * Set when the open file was too long to load whole (see `MAX_EDITOR_LINES`),
 * `null` otherwise.
 *
 * While it is set the buffer is only a *prefix* of the file, so writing it
 * back would delete everything past the cut and running it would run half a
 * program. Every path that saves or runs the buffer therefore checks this
 * first, and the editor is put in read-only mode.
 */
export const currentFileTruncation = writable<Truncation | null>(null);

/** Result of the most recent run, or null before the first one. */
export const runResult = writable<RunResult | null>(null);

/** True while a run is in flight. */
export const running = writable<boolean>(false);

/**
 * Messages from the editor shell itself (file listing failures and the like),
 * kept separate from the program's own output.
 */
export const editorNotice = writable<string>('');

export let ref = writable(0);
