import { redirect } from '@sveltejs/kit';

export const load = async (event) => {
	const session = await event.locals.getSession();

	// console.log ('session',session);
	// console.log ('eventAAAAAAeventAAAAAAeventAAAAAAeventAAAAAAeventAAAAAAeventAAAAAAeventAAAAAA',event);
	if (!session) {
		throw redirect(307, 'signup');
	}

	return {
		session
	};
};
