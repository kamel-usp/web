import { Agent } from 'undici';
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

/** `fetch`, but willing to wait for a slow solver. */
export function runnerFetch(url: string, init: RequestInit = {}): Promise<Response> {
  // `dispatcher` is undici's, and is honoured by Node's global fetch; it is
  // absent from the standard RequestInit type, hence the cast.
  return fetch(url, { ...init, dispatcher: agent } as RequestInit);
}
