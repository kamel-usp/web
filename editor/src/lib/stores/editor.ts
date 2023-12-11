import { writable } from 'svelte/store';

export const editorTerminal = writable<string>('> ');
export const currentFile = writable<string>('');
export const fileContents = writable([]);

export let ref = writable(0);