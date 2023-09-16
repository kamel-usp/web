import { json } from '@sveltejs/kit';

function delay(time) {
	return new Promise(resolve => setTimeout(resolve, time));
} 

/** @type {import('./$types').RequestHandler} */
export async function POST({ request, cookies }) {
	const { code } = await request.json();
	// Mandar para o container manager
	await delay(1000); // Simula a demora
	return json('Ok');
}