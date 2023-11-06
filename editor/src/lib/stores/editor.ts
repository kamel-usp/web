import { writable } from 'svelte/store';

export const editor = writable<string>('# Add your dPasp Code');