/**
 * Authentication is optional.
 *
 * The playground works for anonymous visitors: `$lib/auth.setSessionID` gives
 * each browser a random `fallback_user_id` cookie, and the container manager
 * keys a runner container on whatever id arrives. OAuth only adds a stable
 * identity across browsers, so it is enabled when — and only when — the
 * corresponding credentials are present in the environment.
 *
 * `$env/dynamic/private` is used rather than `$env/static/private` on purpose:
 * the static import fails the *build* when a variable is missing, which is why
 * a fresh clone previously could not start without a GitHub app.
 */

import { SvelteKitAuth } from '@auth/sveltekit';
import GitHub from '@auth/core/providers/github';
import Google from '@auth/core/providers/google';
import { env } from '$env/dynamic/private';
import { sequence } from '@sveltejs/kit/hooks';
import type { Handle } from '@sveltejs/kit';
import { deriveUserId } from '$lib/auth';

const providers = [];

if (env.GITHUB_ID && env.GITHUB_SECRET) {
  providers.push(GitHub({ clientId: env.GITHUB_ID, clientSecret: env.GITHUB_SECRET }));
}

if (env.GOOGLE_ID && env.GOOGLE_SECRET) {
  providers.push(Google({ clientId: env.GOOGLE_ID, clientSecret: env.GOOGLE_SECRET }));
}

/** Used when no provider is configured: no session, no sign-in routes. */
const anonymous: Handle = async ({ event, resolve }) => {
  event.locals.getSession = async () => null;
  return resolve(event);
};

if (providers.length > 0 && !env.AUTH_SECRET) {
  console.warn(
    '[auth] OAuth credentials are set but AUTH_SECRET is not. ' +
      'Set AUTH_SECRET (see editor/.env.example) or sign-in will fail.'
  );
}

const authenticate: Handle =
  providers.length > 0 ? SvelteKitAuth({ providers, trustHost: true }) : anonymous;

/** Days a workspace cookie survives. */
const USER_COOKIE_DAYS = 30;

/**
 * Guarantees a `user_id` cookie before any route runs.
 *
 * The container manager keys a runner container on this id, and the API
 * routes refuse a request without it, so it has to exist by the time the
 * first page renders — not after an `onMount` in the browser.
 */
const identify: Handle = async ({ event, resolve }) => {
  const existing = event.cookies.get('user_id');
  const session = await event.locals.getSession();
  const id = await deriveUserId(session?.user?.email, existing);

  if (id !== existing) {
    event.cookies.set('user_id', id, {
      path: '/',
      httpOnly: true,
      sameSite: 'lax',
      secure: event.url.protocol === 'https:',
      maxAge: 60 * 60 * 24 * USER_COOKIE_DAYS
    });
  }

  // Routes read the id from `locals`, so the first request of a visit works
  // even though its cookie is only being set in this response.
  event.locals.userId = id;

  return resolve(event);
};

export const handle: Handle = sequence(authenticate, identify);
