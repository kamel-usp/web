import { json } from '@sveltejs/kit';

export async function POST ({ params, body }) { 
	var action = params;
	const { container_id } = await request.json();
	console.log(action, container_id);

	// try {
	// 	const cm_response = await fetch(
	// 		`http://container-manager/container_for_user/${id}`
	// 	)

	// 	if (!cm_response.ok) {
	// 	  throw new Error(`Unable to get requested container id from container-manager`);
	// 	}

	// 	const container_id = (await cm_response.json()).id

	// 	console.log(container_id)

	// 	const response = await fetch(
	// 	  `http://dpasp-instance-${container_id}/run`,
	// 	  {
	// 		method: "POST",
	// 		body: body,
	// 		headers: {
	// 		  "Content-Type": "application/json", // Use "Content-Type" with a capital 'C'
	// 		},
	// 	  }
	// 	);

	// 	if (!response.ok) {
	// 	  throw new Error(`HTTP error! Status: ${response.status}`);
	// 	}

	// 	console.log(response.status);
	// 	let code_response = await response.json();
	// 	console.log(code_response);

	// 	return json(code_response);
	// } catch (error) {
	// 	console.error("Error:", error);
	// 	return json({ code: error });
	// }
}