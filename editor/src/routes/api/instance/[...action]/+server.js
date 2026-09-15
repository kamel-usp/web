import { json } from '@sveltejs/kit';
import { get_user_dpasp_runner_url } from '$lib/api';
import { runnerFetch, RUNNER_FETCH_TIMEOUT_MS } from '$lib/runnerFetch';

/** Runner endpoints the browser is allowed to reach. */
const ALLOWED = ['run', 'blob/upload', 'blob/list', 'blob/fetch', 'blob/delete'];

/**
 * Proxies a request to the runner container belonging to the caller.
 *
 * Errors are returned as a body in the runner's own result shape, so the
 * editor's output panel can display them like any other failed run instead of
 * having to special-case transport problems.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ params, request, locals }) {
	const { action } = params;
	// Set by the `identify` hook, so it is present even on the first request
	// of a visit, before the cookie has made it back to the browser.
	const user_id = locals.userId;

	if (!ALLOWED.includes(action)) {
		return runnerError(`Unknown runner endpoint: ${action}`, 404);
	}
	if (!user_id) {
		return runnerError('This session has no workspace id. Reload the page and try again.', 400);
	}

	const body = await request.text();

	let base;
	try {
		base = await get_user_dpasp_runner_url(user_id);
	} catch (e) {
		// `get_user_dpasp_runner_url` throws RunnerUnavailable carrying the
		// container manager's own explanation (for instance that it is still
		// building the runner image). Show that, rather than a guess.
		console.error('container-manager lookup failed:', e instanceof Error ? e.message : e);
		return runnerError(
			e instanceof Error && e.name === 'RunnerUnavailable'
				? e.message
				: 'Could not obtain a dPASP runner for this session.',
			503
		);
	}

	try {
		// runnerFetch, not fetch: a run may take the full DPASP_RUN_TIMEOUT,
		// which exceeds Node's default 300 s header timeout.
		const response = await runnerFetch(`${base}/${action}`, {
			method: 'POST',
			body,
			headers: { 'content-type': 'application/json' }
		});

		if (!response.ok) {
			return runnerError(`The dPASP runner replied ${response.status}.`, 502);
		}

		return json(await response.json());
	} catch (e) {
		console.error(`proxying ${action} failed:`, e);

		// A headers timeout here means the proxy gave up before the runner
		// did, so the runner's own timeout message never arrived. Say that,
		// rather than claiming the runner was unreachable.
		const code = /** @type {{cause?: {code?: string}}} */ (e)?.cause?.code;
		if (code === 'UND_ERR_HEADERS_TIMEOUT' || code === 'UND_ERR_BODY_TIMEOUT') {
			return runnerError(
				`The run was still going after ${Math.round(RUNNER_FETCH_TIMEOUT_MS / 1000)} seconds` +
					' and this proxy stopped waiting. Raise DPASP_PROXY_TIMEOUT_MS (and' +
					' DPASP_RUN_TIMEOUT, which it must stay above) to allow longer runs.',
				504
			);
		}

		// `ENOTFOUND` on a `dpasp-instance-*` name means Docker's embedded DNS
		// has no record of that container — which happens when it is not
		// running. A stopped container is dropped from DNS, so the failure
		// surfaces here, at the far end, as a name that does not exist.
		if (code === 'ENOTFOUND' || code === 'EAI_AGAIN') {
			const host = /** @type {{cause?: {hostname?: string}}} */ (e)?.cause?.hostname ?? '';
			return runnerError(
				`The runner container for this session (${host}) could not be found by name. ` +
					'Docker only resolves containers that are running, so it has most likely ' +
					'exited. The container manager checks for this when it hands one out, so ' +
					'this one died afterwards — its own log says why:\n\n' +
					`    docker logs ${host}\n` +
					'    docker ps -a --filter label=dpasp.role=runner\n\n' +
					'Reloading the page asks the manager for a fresh container.',
				502
			);
		}

		return runnerError('The dPASP runner could not be reached.', 502);
	}
}

/**
 * Builds a body shaped like a failed run, so one renderer handles every case.
 *
 * @param {string} message
 * @param {number} status
 */
function runnerError(message, status) {
	return json(
		{
			ok: false,
			sem: 'stable',
			psem: 'credal',
			interval: true,
			learned: false,
			elapsed_ms: 0,
			queries: [],
			output: '',
			error: { kind: 'internal', type: 'GatewayError', message }
		},
		{ status }
	);
}
