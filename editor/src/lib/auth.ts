/**
 * Derivation of the identifier the container manager keys a runner on.
 *
 * This runs on the server (from `hooks.server.ts`) rather than in the browser.
 * It used to be done in `onMount`, which meant the very first API call of a
 * visit was made before the cookie existed, and so arrived without an id.
 */

/** Hex encoding of a byte buffer. */
function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

/** SHA-256 of a string, hex encoded. */
export async function hashId(message: string): Promise<string> {
  const data = new TextEncoder().encode(message);
  return toHex(await crypto.subtle.digest('SHA-256', data));
}

/** A fresh opaque identifier for an anonymous visitor. */
export function randomId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return toHex(bytes.buffer);
}

/**
 * The identifier for this request.
 *
 * A signed-in user gets a stable id derived from their email, so they return
 * to the same workspace from any browser. Everyone else keeps whatever
 * random id their cookie carries.
 */
export async function deriveUserId(
  email: string | null | undefined,
  existing: string | null | undefined
): Promise<string> {
  if (email) return hashId(email);
  if (existing) return existing;
  return randomId();
}
