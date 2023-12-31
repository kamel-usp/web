import { writable } from 'svelte/store';

export const userID = writable<string>();
export const loggedIn = writable<boolean>();
