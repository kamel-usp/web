/**
 * Where a runner container answers.
 *
 * Kept apart from `api.ts` so that it can be tested without SvelteKit's
 * `$env` machinery: the port here has to match the one in
 * `backend/dPaspRunner/Dockerfile`, and a mismatch would not show up until
 * something is deployed.
 */

/**
 * The port a runner listens on inside its container.
 *
 * 8000 rather than 80 because the runner runs as a non-root user (uid 1000),
 * and binding below 1024 needs `CAP_NET_BIND_SERVICE` — a capability the
 * container deliberately does not have.
 */
export const RUNNER_PORT = 8000;

/**
 * The base URL of one runner, on the internal `dpasp-instances` network.
 *
 * `dpasp-instance-<id>` is the container's *name*, which Docker's embedded
 * DNS resolves on a user-defined network. It used to be a network alias;
 * naming the container is what lets the manager create it directly on the
 * internal network, with no detour through the default bridge.
 */
export function runnerUrl(id: string): string {
  return `http://dpasp-instance-${id}:${RUNNER_PORT}`;
}
