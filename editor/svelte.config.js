import adapter from "@sveltejs/adapter-node";
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  // `vitePreprocess` moved out of `@sveltejs/kit/vite` in SvelteKit 2; it
  // lives in the Vite plugin package now. Importing it from the old place
  // fails at *config load* time, which reads as "svelte-kit sync is broken"
  // rather than as a migration step.
  preprocess: [vitePreprocess()],

  kit: {
    // adapter-node, not adapter-auto: this is deployed to a plain server
    // (see "Running it on a server" in ../README.md), which adapter-auto does
    // not recognise — it printed "Could not detect a supported production
    // environment" on every build and produced nothing runnable. The output
    // is `build/`, started with `node build`.
    adapter: adapter(),
    alias: {
      $lib: "src/lib",
    },
  },
};

export default config;
