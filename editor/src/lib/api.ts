import { env } from '$env/dynamic/private';

/**
 * Asks the container manager for the runner container assigned to a user and
 * returns its base URL on the `dpasp-instances` network.
 *
 * Only reachable from the SvelteKit server, since both hostnames are internal
 * to the compose network.
 *
 * Setting `DPASP_RUNNER_URL` bypasses the container manager and sends every
 * request to a single runner. That is how the stack is run without Docker —
 * `uvicorn main:app` in `backend/dPaspRunner` plus `npm run dev` here — and it
 * must never be set in a deployment, since one runner would then be shared by
 * all users.
 */
export async function get_user_dpasp_runner_url(userid: string): Promise<string> {
  if (env.DPASP_RUNNER_URL) return env.DPASP_RUNNER_URL.replace(/\/+$/, '');

  const cm_response = await fetch(`http://container-manager/container_for_user/${userid}`);

  if (!cm_response.ok) {
    throw new Error(`container-manager replied ${cm_response.status} for user ${userid}`);
  }

  const { id } = (await cm_response.json()) as { id: string };
  if (!id) throw new Error('container-manager returned no container id');

  return `http://dpasp-instance-${id}`;
}
