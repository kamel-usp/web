import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// This file runs in Node, but the project does not depend on `@types/node`.
// Declaring the one global it uses is cheaper than adding the package.
declare const process: { env: Record<string, string | undefined> };

/**
 * Hostnames the dev and preview servers will answer to, from
 * `DPASP_ALLOWED_HOSTS` (comma-separated).
 *
 * Vite refuses requests whose `Host` header it does not recognise, which is
 * what produces
 *
 *     Blocked request. This host ("kamel.ime.usp.br") is not allowed.
 *
 * when the stack is reached by anything other than localhost. The check
 * defends against DNS rebinding: without it, a page on an attacker's domain
 * that resolves to 127.0.0.1 could read from a dev server running on the
 * visitor's machine. So this is a list, not a switch — name the hosts the
 * deployment actually answers to:
 *
 *     DPASP_ALLOWED_HOSTS=kamel.ime.usp.br
 *
 * in a `.env` next to `compose.yaml`. An entry beginning with a dot covers a
 * domain and every subdomain (`.ime.usp.br` allows `kamel.ime.usp.br`).
 * `localhost`, `*.localhost` and bare IP addresses are always allowed, which
 * is why this has never been needed before.
 *
 * The literal `true` disables the check altogether. It is accepted here for
 * the case where something in front of the app already controls which hosts
 * reach it, but it is not the default and should not be used on a machine
 * reachable from a network.
 */
function allowedHosts(): string[] | true {
	const raw = (process.env.DPASP_ALLOWED_HOSTS ?? '').trim();
	if (raw === 'true') return true;
	return raw
		.split(',')
		.map((host) => host.trim())
		.filter((host) => host !== '');
}

export default defineConfig({
	plugins: [sveltekit()],

	// `preview.allowedHosts` falls back to this, so both servers are covered.
	server: {
		allowedHosts: allowedHosts()
	},

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
