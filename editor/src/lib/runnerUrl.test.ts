import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { RUNNER_PORT, runnerUrl } from './runnerUrl';

describe('runnerUrl', () => {
  it('addresses the container by name and port', () => {
    expect(runnerUrl('a1b2c3d4e5f6')).toBe('http://dpasp-instance-a1b2c3d4e5f6:8000');
  });

  it('is above 1024, which is the reason it is not 80', () => {
    // The runner runs as a non-root user with every capability dropped, so
    // it cannot bind a privileged port.
    expect(RUNNER_PORT).toBeGreaterThan(1024);
  });

  it('agrees with the port the runner image listens on', () => {
    // The one cross-file constraint in the request path, and a mismatch
    // would not show up until something is deployed: the editor would build
    // a URL nothing answers on, and every run would report an unreachable
    // runner. Read the Dockerfile and check.
    const dockerfile = readFileSync(
      new URL('../../../backend/dPaspRunner/Dockerfile', import.meta.url),
      'utf8'
    );

    const cmds = [...dockerfile.matchAll(/CMD\s*\[(.+?)\]/g)].map((m) => m[1]);
    expect(cmds.length).toBeGreaterThan(0);

    for (const cmd of cmds) {
      const port = cmd.match(/"--port"\s*,\s*"(\d+)"/);
      expect(port, `no --port in CMD [${cmd}]`).not.toBeNull();
      expect(Number(port![1])).toBe(RUNNER_PORT);
    }
  });

  it('agrees with the image running as a non-root user', () => {
    // If the image went back to root, binding 80 again would be possible and
    // this port would be free to drift.
    const dockerfile = readFileSync(
      new URL('../../../backend/dPaspRunner/Dockerfile', import.meta.url),
      'utf8'
    );

    expect(dockerfile).toMatch(/^USER runner$/m);
  });
});
