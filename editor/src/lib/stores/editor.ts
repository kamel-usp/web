import { writable } from 'svelte/store';

export const editorDpasp = writable<string>('');
export const editorPython = writable<string>('');
export const editorTerminal = writable<string>("empty");