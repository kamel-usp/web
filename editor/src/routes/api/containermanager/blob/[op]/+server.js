import { error, json } from '@sveltejs/kit';
import { get_user_dpasp_runner_url } from '$lib/api';

/**
 * Blob operations against the caller's runner container.
 *
 * Kept for compatibility with older clients; `/api/instance/blob/<op>` is the
 * route the editor uses, and it proxies every runner endpoint uniformly.
 *
 * @type {import('./$types').RequestHandler}
 */
export async function POST({ request, params, locals }) {
	const user_id = locals.userId;
	if (!user_id) throw error(400, 'no workspace id for this session');

	const allowed = ['upload', 'list', 'fetch', 'delete'];
	if (!allowed.includes(params.op)) throw error(404, `unknown blob operation: ${params.op}`);

	try {
		const base = await get_user_dpasp_runner_url(user_id);
		const response = await fetch(`${base}/blob/${params.op}`, {
			method: 'POST',
			body: await request.text(),
			headers: { 'content-type': 'application/json' }
		});

		if (!response.ok) throw error(response.status, `runner replied ${response.status}`);
		return json(await response.json());
	} catch (err) {
		// Re-throw SvelteKit's own HttpError untouched; wrap anything else.
		if (err && typeof err === 'object' && 'status' in err) throw err;
		console.error('blob proxy failed:', err);
		throw error(502, 'could not reach the dPASP runner');
	}
}
