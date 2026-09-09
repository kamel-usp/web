# dPASP Playground (web)

A browser front end for [dPASP](https://github.com/kamel-usp/dpasp): write a
`.pasp` program with syntax highlighting, upload CSV data files, run it, and
read the query probabilities.

## Layout

```
web/
├── compose.yaml            orchestration for the three pieces below
├── editor/                 SvelteKit front end (port 8000)
└── backend/
    ├── main.py             container manager (port 8001)
    ├── containerManager/    one runner container per user, with a reaper
    └── dPaspRunner/        the runner image: FastAPI + dPASP (port 80)
```

Request path for a run:

```
browser
  → POST /api/instance/run                (SvelteKit server route)
    → GET  container-manager/container_for_user/<id>
    → POST dpasp-instance-<cid>/run       (FastAPI in the user's container)
      → runner_worker.py                  (separate process, rlimited, killable)
        → pasp.parse / Program.__call__
```

The front end never talks to a runner container directly: the runner
hostnames only exist on the internal `dpasp-instances` network, and the
SvelteKit server route is what resolves which container belongs to the caller.

## Running it

### With Docker

```bash
cd web
docker compose --profile dpasp up --build     # real dPASP
docker compose --profile mock  up --build     # random numbers, no solver
```

Then open <http://localhost:8000>. The `mock` profile is useful for front-end
work: it skips building the dPASP image, which pulls PyTorch.

No secrets are needed. Every visitor gets an anonymous workspace keyed by a
cookie. To add persistent logins, copy `editor/.env.example`, fill it in, and
put the values in a `.env` file next to `compose.yaml`; the sign-in link
appears only once credentials are configured.

#### The container manager needs a reachable Docker socket

It creates the runner containers, so it mounts the host's Docker socket. If
the daemon's socket is not at `/var/run/docker.sock` — which is the case under
colima, where it lives beneath `~/.colima/<profile>/` — point `DOCKER_SOCKET`
at the real one, in a `.env` file next to `compose.yaml` or exported:

```bash
DOCKER_SOCKET=$(docker context inspect -f '{{.Endpoints.docker.Host}}' \
  | sed 's|^unix://||')
```

#### Where clingo comes from (and why not from apt)

The runner image does **not** install clingo from a package repository.
`ppa:potassco/stable` publishes clingo for amd64 and i386 only — there is no
arm64 build, confirmed against the Launchpad API — so on an Apple Silicon Mac
the PPA is added successfully and then:

```
E: Package 'clingo' has no installation candidate
```

Adding the repository is not the fix; no candidate exists for the
architecture. Ubuntu's own universe clingo is too old for dPASP.

Instead, the clingo **wheel** from PyPI supplies both sides of the
dependency: it ships `clingo.h` and a shared object exporting the full clingo
C API, and it publishes aarch64 wheels. The image installs it with pip, then
presents it to the compiler through a conventional `-I`/`-l` layout under
`/opt/clingo` and builds `pasp-plp` against that. Filenames embed the Python
version and architecture (`_clingo.cpython-310-aarch64-linux-gnu.so`), so
they are discovered at build time rather than hardcoded, and the runpath
points at the wheel's own directory — the linker records that shared object's
real name as the dependency, and that is exactly where it lives.

`ppa:deadsnakes/ppa` is gone too: jammy ships Python 3.10 as its default
`python3`, so the interpreter needed no PPA either. That removed
`software-properties-common`, `python3-launchpadlib` and two `apt-get update`
passes from the build.

The image ends the dPASP stage by running a one-line program and asserting the
answer, so a broken build fails during `docker compose build` rather than at
a user's first query.

#### The editor says it cannot obtain a runner, or the log shows `ECONNREFUSED`

On a cold start this is expected for a few minutes, and the first build is the
slow one: it compiles dPASP against clingo and downloads PyTorch. Watch it:

```bash
docker compose logs -f container-manager     # "Done building image!" when finished
curl localhost:8001/health                   # {"status":"building"|"ready"|"error"}
```

The container manager builds the runner image during its own startup, but it
no longer does so *inside* uvicorn's lifespan. Uvicorn binds its listening
socket only after the lifespan's startup block returns, so building there made
the whole API refuse connections for the duration — the frontend logged

```
container-manager lookup failed: TypeError: fetch failed
  [cause]: Error: connect ECONNREFUSED 172.18.0.3:80
```

which says nothing about the real cause. The build is now awaited as a
background task: the API answers immediately and returns `503` with an
explanation while it warms up, and the editor displays that explanation.

If `/health` reports `"status": "error"`, the build itself failed and `detail`
carries the reason.

#### `failed to set up container networking: network <id> not found`

A leftover runner container is holding an endpoint on a network that no longer
exists. Runner containers are created through the Docker API, not by Compose,
so `docker compose down` never removed them — and `down -v` deleted the
`dpasp-instances` network out from under them.

`deleteContainer` now removes containers instead of merely stopping them, and
the manager sweeps leftovers at startup, so this should not recur. To clear an
existing pile:

```bash
docker compose --profile dpasp down -v --remove-orphans
docker ps -aq --filter label=dpasp.role=runner | xargs -r docker rm -f
# containers from before the label existed:
docker ps -aq --filter ancestor=dpasp-runner | xargs -r docker rm -f
docker network prune -f
docker compose --profile dpasp up --build
```

If it survives that, the daemon's own network state is wedged; under colima,
`colima restart` clears it.

#### `unable to resolve docker endpoint: context "..." not found`

Not a problem with this stack: the Docker CLI cannot start at all, because
`~/.docker/config.json` names a `currentContext` whose metadata no longer
exists under `~/.docker/contexts/meta/`. It happens after a `colima delete`,
an uninstall, or a cleanup of `~/.docker`. To recover:

```bash
docker context ls                    # may itself fail with the same error
docker context use default           # point the CLI at a context that exists
```

If even `docker context use` fails, clear the stale entry and retry:

```bash
cp ~/.docker/config.json ~/.docker/config.json.bak
python3 -c "import json,pathlib; p=pathlib.Path.home()/'.docker/config.json'; \
c=json.loads(p.read_text()); c.pop('currentContext',None); \
p.write_text(json.dumps(c,indent=2))"
```

Also check for a stale override in your shell: `env | grep -i '^DOCKER'`.
`DOCKER_CONTEXT` and `DOCKER_HOST` both win over `config.json`.

That only fixes the CLI. A daemon still has to be listening — `colima start`
(which recreates both the socket and the `colima` context), or launch Docker
Desktop. Confirm with `docker context ls` and `docker info`.

### Without Docker

Useful for front-end work and for debugging the runner. Two terminals:

```bash
# 1. the runner, with dPASP importable in the environment
cd web/backend/dPaspRunner
DPASP_BLOB_FOLDER=/tmp/blobs uvicorn main:app --port 8100

# 2. the front end, pointed straight at that runner
cd web/editor
npm install
DPASP_RUNNER_URL=http://127.0.0.1:8100 npm run dev -- --port 5173
```

`DPASP_RUNNER_URL` bypasses the container manager and sends every request to
one runner. It exists for local development only — set in a deployment, all
users would share a single workspace.

## The runner's result format

`POST /run` takes `{sem, psem, code}` and always answers `200` with a body of
this shape. A faulty program is not an HTTP error: it comes back with
`ok: false` and a structured `error`, so the editor renders it in the output
panel like any other outcome.

```json
{
  "ok": true,
  "sem": "stable",
  "psem": "credal",
  "interval": true,
  "learned": false,
  "elapsed_ms": 218,
  "queries": [
    { "query": "ℙ(alarm | burglary)", "values": [0.9, 0.9],
      "lower": 0.9, "upper": 0.9 }
  ],
  "output": "",
  "error": null
}
```

- `interval` is true under the credal semantics, where each query yields
  `[lower, upper]`, and false under max-entropy, where it yields one value.
- A `#semantics` directive inside the program wins over the UI selection, as
  it does in the `pasp` CLI; `psem` reports what was actually used.
- Non-finite bounds are sent as the strings `"inf"`, `"-inf"` and `"nan"`,
  because JSON has no literals for them and `JSON.parse` rejects the
  alternatives.
- `output` is only what the program itself printed. dPASP's progress bar and
  its import-time notices are stripped.
- `error.kind` is one of `parse`, `runtime`, `timeout`, `internal`. Parse
  errors carry `line` and `column`.

### Why the runner forks a process

`runner_worker.py` runs each program in a child process rather than in the
FastAPI worker. Three reasons:

1. dPASP's inference core writes its progress bar and results from C, on file
   descriptors 1 and 2. `redirect_stdout` cannot see that output, and
   redirecting the descriptors in-process would capture uvicorn's own output
   and race between concurrent requests.
2. Grounding is not guaranteed to terminate, and exact inference enumerates
   every total choice — cost grows exponentially in the number of
   probabilistic facts. A child can carry an rlimit and be killed on a
   deadline; an event-loop task cannot.
3. A segfault in the C extension takes down only the child.

Tunable through the environment: `DPASP_RUN_TIMEOUT` (default 30 s),
`DPASP_RUN_MEM_MB` (default 1024), `DPASP_MAX_OUTPUT` (default 65536 chars).
These sit inside the runner container and complement, not replace, whatever
CPU and memory limits the container itself is given.

## Syntax highlighting

`editor/src/lib/lang/pasp.ts` is a CodeMirror 6 language for dPASP, ported
from the Pygments lexer in `pygments_pasp/`. It covers probabilistic, credal
and learnable annotations, annotated disjunctions, rules, directives, neural
rules with their `with optim = ...` options, the `test`/`train` data sources,
and `#python ... #end.` blocks — whose bodies are handed to CodeMirror's
Python mode, mirroring the Pygments lexer's `using(PythonLexer)`.

One deliberate difference from `pygments_pasp`: it does **not** highlight
`%* ... *%` block comments. That is a clingo feature which the Pygments lexer
inherited, but dPASP's own grammar defines only

```
COMMENT: "%" /[^\n]*/ NEWLINE
```

so the parser rejects a block comment's continuation lines. Highlighting them
as comments would hide the resulting syntax error instead of revealing it.

## Tests

```bash
cd web/editor && npm test              # 25 tests: the pasp tokenizer
cd web/editor && npm run check         # svelte-check: 0 errors

# backend tests need the test-only extras:
#   cd web/backend && pip install -r requirements-dev.txt
cd web/backend && python3 -m pytest test_main.py      #  6: startup, readiness
cd web/backend/containerManager && python3 -m pytest  # 18: queue, lifecycle
cd web/backend/dPaspRunner && python3 -m pytest       # 15: result format, limits
```

The runner tests that need dPASP skip themselves when it is not importable,
so they are still useful in a checkout that only runs the mock target.

## Build warnings

`docker compose up` used to print a wall of npm and apt noise on every start.
What it was, and what was done:

| Warning | Cause | Fix |
| --- | --- | --- |
| npm deprecation notices for `uuid@9` | `google-auth-library`, which was declared but never imported — the Google provider comes from `@auth/core` | dependency removed |
| "New major version of npm available", funding and audit footers | npm's own notices, printed on each install | `NPM_CONFIG_UPDATE_NOTIFIER` / `_FUND` / `_AUDIT` in `editor/Dockerfile` |
| The whole install log, on **every** `docker compose up` | the dev image ran `npm install` at container start, because the source bind mount hid the image's `node_modules` | `npm ci` in a cached build layer plus the `editor_node_modules` volume |
| "Some chunks are larger than 500 kB" | CodeMirror and flowbite bundled into the 527 kB page chunk | `manualChunks` in `vite.config.ts` splits them out; the page chunk is now 48 kB |
| "apt does not have a stable CLI interface" | `apt` used in `dPaspRunner/Dockerfile` | switched to `apt-get` |
| debconf frontend warnings | interactive apt in a non-interactive build | `DEBIAN_FRONTEND=noninteractive` |
| pip's root-user warning and version check | normal in a container, not actionable from inside the image | `PIP_ROOT_USER_ACTION` / `PIP_DISABLE_PIP_VERSION_CHECK` |
| `FromAsCasing` and `LegacyKeyValueFormat` from BuildKit | `FROM ... as` and `ENV key value` in `editor/Dockerfile` | `AS` and `ENV key=value`; the unused `cm_host` variable was dropped |
| A theme object printed to the server log on every render | a leftover `console.log` in `svelte-themes`, whose `<SvelteTheme />` did nothing — `app.html` hardcodes `class="dark"` and there is no theme toggle | dependency and component removed |
| `inflight@1.0.6` "leaks memory", plus `rimraf@2` and `glob@7` | one chain under `svelte-check` 3: `svelte-check → svelte-preprocess → sorcery → sander → rimraf@2 → glob@7 → inflight` | `svelte-check` upgraded to 4.x, which dropped `svelte-preprocess` from its dependencies and takes the whole chain with it (24 packages) |

`npm install` is now warning-free from a clean cache — no deprecation notices
at all. `--force` is gone too: the dependency set resolves on its own, so the
flag (and its "I sure hope you know what you are doing" warning) was stale.

Two notes on the `svelte-check` 4 upgrade:

- It works on Svelte 4; its peer range is `^4.0.0 || ^5.0.0-next.0`, so this
  did **not** require the Svelte 5 migration.
- TypeScript is pinned to `~5.4.5`. SvelteKit 1.30.4 — the latest 1.x —
  generates a `.svelte-kit/tsconfig.json` containing `importsNotUsedAsValues`
  and `preserveValueImports`, which TypeScript 5.5 removed; on TS 5.9,
  `svelte-check` reports two warnings about them that cannot be cleared from
  our own `tsconfig.json`, since the options come from the generated parent.
  Unpin TypeScript when moving to SvelteKit 2.

Resist silencing a deprecated transitive dependency with an npm `override`
unless the replacement is API-compatible. The tempting fix here —
`overrides: { rimraf, glob }` — quietly breaks `sander`, which calls
`rimraf(target, callback)` while rimraf 4+ exports an object rather than a
callable. It appears to work only because `sorcery` never calls that path.

A note on the `editor_node_modules` volume: because it persists, a change to
`package.json` needs both the image and the volume refreshed.

```bash
docker compose down -v && docker compose --profile dpasp up --build
```

## Known gaps

- **`npm audit` reports 17 vulnerabilities, 3 of them critical.** They are
  not stray dependencies; they all trace to the pinned generation of the
  framework — Svelte 4 / SvelteKit 1 / Vite 4, plus `@auth/core` 0.15 and the
  `vitest` that pins to Vite 4. Every fix `npm audit` offers is a major
  version bump, so clearing them means a Svelte 5 + SvelteKit 2 + Vite 5
  migration rather than a dependency tweak. Deprecation warnings are already
  clear; this is the remaining dependency debt.
- **Runner containers have no resource limits.** `containerManager` creates
  them with `client.containers.run(...)` and no `cpu_quota`, `mem_limit`,
  `pids_limit`, `cap_drop` or `read_only`. The per-run timeout and rlimit
  above bound one program; they do not bound a container.
- **`pruneContainers` is never called.** Nothing schedules it, so containers
  live until the process exits rather than expiring after their configured
  lifetime. They are at least removed rather than left stopped now, and
  leftovers are swept at startup, but nothing enforces the lifetime while the
  manager runs.
- **The container manager mounts the Docker socket**, which gives the web tier
  root-equivalent control of the host.
- **Learning is untested here.** A `#learn` program is dispatched correctly
  (`Program.__call__` handles it) but needs PyTorch and uploaded data; the
  result format reports it only through the `learned` flag.
- **CSV files are uploaded but not otherwise interpreted.** They land in the
  runner's blob folder, which is the working directory for a run, so a
  `#python` block can open one by its bare name. There is no schema
  inspection or preview.
