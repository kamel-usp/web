import { json } from '@sveltejs/kit';
import { get_user_dpasp_runner_url } from '$lib/api';

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
		console.error('container-manager lookup failed:', e);
		return runnerError(
			'Could not obtain a dPASP runner for this session. The container manager may be starting up or out of capacity.',
			503
		);
	}

	try {
		const response = await fetch(`${base}/${action}`, {
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
