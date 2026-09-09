// See https://kit.svelte.dev/docs/types#app
// for information about these interfaces
declare global {
	namespace App {
		interface Locals {
			/**
			 * Identifier the container manager keys this visitor's runner on.
			 * Set for every request by the `identify` hook in hooks.server.ts.
			 */
			userId: string;
		}
		// interface Error {}
		// interface PageData {}
		// interface Platform {}
	}
}

export {};
