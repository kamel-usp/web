import { env } from '$env/dynamic/private';

/** Raised with the container manager's own explanation, when it gives one. */
export class RunnerUnavailable extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RunnerUnavailable';
  }
}

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

  let response: Response;
  try {
    response = await fetch(`http://container-manager/container_for_user/${userid}`);
  } catch (e) {
    // The manager is unreachable rather than unhappy. While it builds the
    // runner image it is not yet listening at all, because uvicorn binds its
    // socket only after startup finishes.
    throw new RunnerUnavailable(
      'The container manager is not answering yet. If the stack has just been ' +
        'started it is probably still building the dPASP runner image, which ' +
        'takes several minutes the first time. Check: ' +
        'docker compose logs -f container-manager'
    );
  }

  if (!response.ok) {
    // 503 carries the manager's own explanation — pass it through rather than
    // replacing it with a generic message.
    let detail = '';
    try {
      const body = await response.json();
      if (body && typeof body.error === 'string') detail = body.error;
    } catch (e) {
      /* no JSON body; fall back to the status */
    }
    throw new RunnerUnavailable(
      detail || `The container manager replied ${response.status}.`
    );
  }

  const { id } = (await response.json()) as { id: string };
  if (!id) throw new RunnerUnavailable('The container manager returned no container id.');

  return `http://dpasp-instance-${id}`;
}
