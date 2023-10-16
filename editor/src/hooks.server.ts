import { SvelteKitAuth } from "@auth/sveltekit";
import GitHub from "@auth/core/providers/github";
import GoogleProvider from '@auth/core/providers/google';
import { GITHUB_ID, GITHUB_SECRET, GOOGLE_ID, GOOGLE_SECRET } from "$env/static/private";

// export const handle = SvelteKitAuth({
//   providers: [GitHub({ clientId: GITHUB_ID, clientSecret: GITHUB_SECRET })],
// });
// export const handle = async ({ event, resolve }) => {
//   const response = await resolve(event);
//   return response;
// };
export const handle = SvelteKitAuth({
  providers: [GitHub({ clientId: GITHUB_ID, clientSecret: GITHUB_SECRET }), 
              GoogleProvider({ clientId: GOOGLE_ID, clientSecret: GOOGLE_SECRET })]
 });