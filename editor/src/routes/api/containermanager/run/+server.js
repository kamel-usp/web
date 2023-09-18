import { json } from '@sveltejs/kit';

function delay(time) {
	return new Promise(resolve => setTimeout(resolve, time));
} 

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, cookies }) {
	const { code } = await request.json();

	// return json({ code });

	try {
		const response = await fetch(
		  "http://localhost:8000/api",
		  {
			method: "POST",
			body: JSON.stringify({ code }),
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