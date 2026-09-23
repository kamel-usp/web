import type { LayoutServerLoad } from './$types';
import { env } from '$env/dynamic/private';

/**
 * `authEnabled` tells the layout whether to offer sign-in at all. Without
 * OAuth credentials there are no `/auth/*` routes, so the links would 404.
 */
export const load: LayoutServerLoad = async (event) => {
  const authEnabled = Boolean(
    (env.GITHUB_ID && env.GITHUB_SECRET) || (env.GOOGLE_ID && env.GOOGLE_SECRET)
  );

  return {
    session: await event.locals.auth(),
    authEnabled
  };
};
