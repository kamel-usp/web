import { writable } from 'svelte/store';
import type { RunResult } from '$lib/types';

export const currentFileContent = writable<string>('');
export const currentFile = writable<string>('');

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
