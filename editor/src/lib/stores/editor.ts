import { writable } from 'svelte/store';

export const editor = writable<string>('');
