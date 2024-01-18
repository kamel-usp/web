import { writable } from 'svelte/store';

export const editorTerminal = writable<string>('> ');
export const currentFileContent = writable<string>('');
export const currentFile = writable<string>('');

export let ref = writable(0);