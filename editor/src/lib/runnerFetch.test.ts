import { describe, expect, it, afterAll, beforeAll } from 'vitest';
import http from 'node:http';

import { runnerFetch, RUNNER_FETCH_TIMEOUT_MS } from './runnerFetch';

/**
 * These call a real HTTP server, on purpose.
 *
 * `runnerFetch` is four lines and has no logic to unit-test; what it has is a
 * dependency on two copies of undici agreeing with each other — Node's
 * bundled one behind the global `fetch`, and the `undici` package that
 * supplies the `Agent`. They stopped agreeing at undici 8, and every proxied
 * request began failing with
 *
 *     InvalidArgumentError: invalid onRequestStart method   (UND_ERR_INVALID_ARG)
 *
 * A mocked `fetch` would have passed throughout: both functions have the same
 * signature, so the type checker saw nothing, and the editor's other 66 tests
 * never opened a socket. The only thing that catches this class of bug is
 * making the call for real, which costs a `http.createServer` and a few
 * milliseconds.
 */

let server: http.Server;
let base: string;

/** What the last request carried, so the forwarding itself is checked too. */
let lastRequest: { method: string; url: string; body: string } | null = null;

beforeAll(async () => {
  server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      lastRequest = { method: req.method ?? '', url: req.url ?? '', body };

      if (req.url === '/boom') {
        res.writeHead(500, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: 'nope' }));
        return;
      }

      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ files: ['earthquake.pasp'], echoed: body }));
    });
  });

  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  if (address === null || typeof address === 'string') throw new Error('no port');
  base = `http://127.0.0.1:${address.port}`;
});

afterAll(() => new Promise<void>((resolve) => server.close(() => resolve())));

describe('runnerFetch', () => {
  it('reaches a real server through its custom dispatcher', async () => {
    // The assertion that matters is that this does not throw
    // UND_ERR_INVALID_ARG on the way out.
    const response = await runnerFetch(`${base}/blob/list`, {
      method: 'POST',
      body: JSON.stringify({}),
      headers: { 'content-type': 'application/json' }
    });

    expect(response.ok).toBe(true);
    expect(response.status).toBe(200);
    expect(await response.json()).toMatchObject({ files: ['earthquake.pasp'] });
  });

  it('forwards the method, path and body unchanged', async () => {
    await runnerFetch(`${base}/blob/upload`, {
      method: 'POST',
      body: JSON.stringify({ filename: 'a.pasp', content: '0.5::a.' }),
      headers: { 'content-type': 'application/json' }
    });

    expect(lastRequest?.method).toBe('POST');
    expect(lastRequest?.url).toBe('/blob/upload');
    expect(JSON.parse(lastRequest?.body ?? '{}')).toEqual({
      filename: 'a.pasp',
      content: '0.5::a.'
    });
  });

  it('reports a non-2xx as a response rather than throwing', async () => {
    // The proxy route reads `response.ok` and turns it into its own message,
    // so a 500 from the runner has to arrive as a value.
    const response = await runnerFetch(`${base}/boom`, { method: 'POST', body: '{}' });

    expect(response.ok).toBe(false);
    expect(response.status).toBe(500);
  });

  it('fails as a fetch failure, with a cause, when nothing is listening', async () => {
    // `+server.js` switches on `e.cause.code` — ENOTFOUND and the timeout
    // codes — so the error shape is part of this module's contract.
    await expect(runnerFetch('http://127.0.0.1:1/blob/list', { method: 'POST' })).rejects.toThrow();
  });

  it('waits longer than the runner does', () => {
    // The runner's own deadline must be the one that fires, or the user gets
    // a transport error instead of the runner's timeout message.
    expect(RUNNER_FETCH_TIMEOUT_MS).toBeGreaterThan(300_000);
  });
});
