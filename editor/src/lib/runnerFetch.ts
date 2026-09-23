import { Agent, fetch as undiciFetch } from 'undici';
import { env } from '$env/dynamic/private';

/**
 * Requests to a runner container, with a timeout long enough for a full run.
 *
 * A run is bounded by `DPASP_RUN_TIMEOUT` on the runner, five minutes by
 * default, and the proxy holds the connection open for the whole of it. That
 * collides with Node's default: its `fetch` is undici, whose `headersTimeout`
 * is 300 s, so a run allowed to take 300 s races the client that is waiting
 * for it and can fail with
 *
 *     UND_ERR_HEADERS_TIMEOUT
 *
 * which tells the user nothing about their program. Rather than depend on
 * that default — it is invisible in the code and would bite again the moment
 * the run limit is raised — the timeout is set explicitly here, above the
 * run limit, so the runner's own deadline is always the one that fires and
 * the user gets the timeout message the runner wrote.
 */
export const RUNNER_FETCH_TIMEOUT_MS = Number(env.DPASP_PROXY_TIMEOUT_MS || 330_000);

const agent = new Agent({
  headersTimeout: RUNNER_FETCH_TIMEOUT_MS,
  bodyTimeout: RUNNER_FETCH_TIMEOUT_MS
});

/**
 * `fetch`, but willing to wait for a slow solver.
 *
 * **undici's `fetch`, not the global one.** Node's `fetch` is its own bundled
 * copy of undici, and a `dispatcher` from the `undici` package on npm is a
 * *different* copy. The two agreed for long enough to be mistaken for one
 * library — and then stopped, when undici 8 changed the handler interface a
 * dispatcher is called through. Node's fetch built a handler of its bundled
 * version's shape, the userland `Agent` validated it, and every proxied
 * request died before it left the process:
 *
 *     proxying blob/list failed: TypeError: fetch failed
 *       [cause]: InvalidArgumentError: invalid onRequestStart method
 *         at assertRequestHandler (undici/lib/core/util.js:573:11)
 *         ...  code: 'UND_ERR_INVALID_ARG'
 *
 * Taking the `fetch` from the same package as the `Agent` removes the seam
 * rather than lining the two copies up: nothing here now depends on which
 * undici the Node image happens to bundle. `runnerFetch.test.ts` exercises
 * this against a real HTTP server, because the mismatch is invisible to the
 * type checker — both `fetch`es have the same signature.
 */
export function runnerFetch(url: string, init: RequestInit = {}): Promise<Response> {
  // undici's own RequestInit accepts `dispatcher`; the DOM one this file is
  // typed against does not, hence the casts. The returned Response is
  // spec-compatible — `.ok`, `.status` and `.json()` are all that callers use.
  return undiciFetch(url, { ...init, dispatcher: agent } as never) as unknown as Promise<Response>;
}
