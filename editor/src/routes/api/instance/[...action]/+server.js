import { json } from '@sveltejs/kit';

export async function POST ({ params, request, cookies }) {
	const { body, headers } = request
	const { action } = params;
	const user_id = cookies.get("user_id");
	console.log(action, user_id);

	try {
		const cm_response = await fetch(
			`http://container-manager/container_for_user/${user_id}`
		)

		if (!cm_response.ok) {
		  throw new Error(`Unable to get requested container id from container-manager`);
		}

		const container_id = (await cm_response.json()).id

		console.log(container_id)
		const response = await fetch(
		  `http://dpasp-instance-${container_id}/${action}`,
		  {
			method: "POST",
			body: body,
			headers: headers,
			duplex: "half",
		  }
		);

		if (!response.ok) {
		  throw new Error(`HTTP error! Status: ${response.status}`);
		}

		return response
	} catch (error) {
		console.error("Error:", error);
		return { code: error };
	}
}
