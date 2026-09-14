import adapter from "@sveltejs/adapter-node";
import { vitePreprocess } from "@sveltejs/kit/vite";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  // Consult https://kit.svelte.dev/docs/integrations#preprocessors
  // for more information about preprocessors
  preprocess: [vitePreprocess({})],

  kit: {
    // adapter-node, not adapter-auto: this is deployed to a plain server
    // (see "Running it on a server" in ../README.md), which adapter-auto does
    // not recognise — it printed "Could not detect a supported production
    // environment" on every build and produced nothing runnable. The output
    // is `build/`, started with `node build`.
    //
    // Pinned to 1.x: adapter-node 2+ requires SvelteKit 2, and this project
    // is on SvelteKit 1.30.4.
    adapter: adapter(),
    alias: {
      $lib: "src/lib",
    },
  },
};

export default config;
