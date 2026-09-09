import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],

	build: {
		rollupOptions: {
			output: {
				/**
				 * Split the two large vendor groups out of the page chunk.
				 *
				 * Everything landed in one 527 kB chunk before this, which
				 * tripped Rollup's 500 kB warning. CodeMirror and its Lezer
				 * grammars are the bulk of it, and they change far less often
				 * than the app code, so giving them their own chunk both
				 * silences the warning and lets a browser keep them cached
				 * across deploys.
				 *
				 * Only `node_modules` ids are matched. The SSR build
				 * externalises those rather than bundling them, so this
				 * affects the client build alone.
				 */
				manualChunks(id: string) {
					if (!id.includes('node_modules')) return;

					if (
						id.includes('@codemirror') ||
						id.includes('@lezer') ||
						id.includes('style-mod') ||
						id.includes('w3c-keyname') ||
						id.includes('crelt')
					) {
						return 'codemirror';
					}

					if (id.includes('flowbite')) return 'flowbite';
				}
			}
		}
	}
});
