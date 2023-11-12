import { json } from '@sveltejs/kit';

function delay(time) {
	return new Promise(resolve => setTimeout(resolve, time));
}

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, cookies }) {
	const { code, sem, psem, user_id } = await request.json();
	console.log(code, sem, psem, user_id);

	try {
		const cm_response = await fetch(
			`http://container-manager/container_for_user/${user_id}`
		)

		if (!cm_response.ok) {
		  throw new Error(`Unable to get requested container id from container-manager`);
		}

		const container_id = (await cm_response.json()).id

		console.log("CONTAINER ID: ", container_id)

		const response = await fetch(
		  `http://dpasp-instance-${container_id}/run`,
		  {
			method: "POST",
			body: JSON.stringify({ sem, psem, code }),
			headers: {
			  "Content-Type": "application/json", // Use "Content-Type" with a capital 'C'
			},
		  }
		);

		if (!response.ok) {
		  throw new Error(`HTTP error! Status: ${response.status}`);
		}

		console.log(response.status);
		let code_response = await response.json();
		console.log(code_response);

		return json(code_response);
	} catch (error) {
		console.error("Error:", error);
		return json({ code: error });
	}
}
