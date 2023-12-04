import { fail } from '@sveltejs/kit';
import { get_user_dpasp_runner_url } from '$lib/api';

/** @type {import('./$types').RequestHandler} */
export async function POST({request, url}) {
    try {
        console.log("oi eu recebi uma request")
        const data = await request.request()
        const response = await fetch(
            `${get_user_dpasp_runner_url(10)}/${url.params.op}`,
            {
                method: "POST",
                body: request.body,
                headers: request.headers,
            }
        );
    } catch (err) {
        throw fail(500, { err: err })
    }
}