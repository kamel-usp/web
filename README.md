# dPASP Playground (web)

A browser front end for [dPASP](https://github.com/kamel-usp/dpasp): write a
`.pasp` program with syntax highlighting, upload CSV data files, run it, and
read the query probabilities.

## Layout

```
web/
├── compose.yaml            orchestration for the pieces below
├── editor/                 SvelteKit front end (port 8000)
└── backend/
    ├── main.py             container manager (port 8001)
    ├── containerManager/   one runner container per user, with a reaper
    ├── dockerProxy/        the only container that holds the Docker socket;
    │                       an allowlist in front of the daemon (port 2375,
    │                       internal)
    └── dPaspRunner/        the runner image: FastAPI + dPASP (port 8000,
                            as a non-root user)
```

Request path for a run:

```
browser
  → POST /api/instance/run                (SvelteKit server route)
    → GET  container-manager/container_for_user/<id>
    →                                     (creating one, if needed, through
    →                                      docker-proxy → the Docker daemon)
    → POST dpasp-instance-<cid>/run       (FastAPI in the user's container)
      → runner_worker.py                  (separate process, rlimited, killable)
        → pasp.parse / Program.__call__
```

The front end never talks to a runner container directly: the runner
hostnames only exist on the internal `dpasp-instances` network, and the
SvelteKit server route is what resolves which container belongs to the caller.

The title bar links to the dPASP language tutorial at
<https://kamel-usp.github.io/pages/learn_dpasp.html>, in a new tab — it is the
one link that leaves the app, and the page holds unsaved buffers and possibly a
run in flight.

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

#### The stack needs a reachable Docker socket

Runner containers are created through the Docker API, so the socket has to be
mounted — into `docker-proxy`, which is the only service that gets it (see
*What bounds the container manager*). If the daemon's socket is not at
`/var/run/docker.sock` — which is the case under colima, where it lives
beneath `~/.colima/<profile>/` — point `DOCKER_SOCKET` at the real one, in a
`.env` file next to `compose.yaml` or exported:

```bash
DOCKER_SOCKET=$(docker context inspect -f '{{.Endpoints.docker.Host}}' \
  | sed 's|^unix://||')
```

#### `refused by the dPASP docker proxy: …`

The manager asked the daemon for something the proxy's allowlist does not
cover, and `docker compose logs docker-proxy` has the matching `DENY` line
with the reason. This is working as intended — it means a call was added to
the manager without a corresponding decision in
`backend/dockerProxy/policy.py`.

Allow it there, deliberately and with a test, rather than by widening a rule:
the file is short on purpose, and `policy.decide` is a pure function, so a new
rule costs one test in `test_policy.py` and one line in the allowlist.

```bash
docker compose --profile dpasp logs docker-proxy | grep DENY
```

If the manager instead prints **`WARNING: Docker access is a direct socket`**
at startup, it is talking to the daemon directly and the proxy is not in the
path at all — check that `DOCKER_HOST` reached it (`docker compose config`).

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

#### `…so: failed to map segment from shared object`

The dynamic loader could not `mmap` part of a library while the runner was
loading dPASP. Two different causes produced it here, both now fixed:

- **`libtorch_python.so`** — the per-run memory limit capped the virtual
  address space (`RLIMIT_AS`) rather than the heap. Address space includes
  file-backed library mappings, and PyTorch maps far more of it than it uses.
  The limit is `RLIMIT_DATA` now.
- **`libc10_cuda.so`, on x86_64 only** — the heap limit was applied *before*
  the runner imported dPASP, so the runtime's own loading had to fit inside
  the user's budget. On x86_64 `pip install torch` installs the **CUDA**
  build, and `import pasp` then holds about 790 MB of data mappings — most of
  the 1024 MB default. On arm64 the wheel has no CUDA libraries, so the same
  image was comfortably inside the budget: it failed on Linux/x86_64 and
  worked on Apple Silicon. Two changes: the limit is applied *after* the
  imports and counts only what the program itself allocates, and the image
  now installs CPU-only torch (see the `TORCH_INDEX` build argument).

Measured here with the CUDA build installed, importing dPASP with the limit
applied first: 1024 MB works, 512 MB gives the message above, 256 MB
**segfaults inside the dynamic loader** before Python can raise. With the
limit applied afterwards, all three import cleanly and still refuse a
runaway allocation.

If it comes back, the question is what is bounding a mapping: check that
nothing sets `RLIMIT_AS`, and that the heap budget is still applied after the
imports rather than before.

#### Nothing answers on <http://localhost:8000>

The dev frontend exited instead of serving. `docker compose --profile dpasp
logs frontend` says which of these it was; the first is by far the most
likely.

**`Cannot find package '@sveltejs/adapter-node' imported from
/app/svelte.config.js`** — the `editor_node_modules` volume is older than
`package.json`. Docker fills a *named* volume from the image only when the
volume is empty, and `up --build` rebuilds images without touching volumes,
so a dependency added since the volume was created is simply not there.
`npm run dev` starts with `svelte-kit sync`, which loads `svelte.config.js`,
which imports the adapter — so the script dies before `vite dev` runs, and
nothing listens at all.

The dev image now repairs this itself: it keeps its installed tree at
`/opt/node_modules` and its entrypoint copies that into the volume whenever
the volume's stamped lockfile hash differs from the current one. If you are
on an image built before that, clear the volume once:

```bash
docker compose --profile dpasp down -v
docker compose --profile dpasp up --build
```

**Nothing at all in the log, and `docker compose ps` shows no frontend** —
check the profile. Every service in this file belongs to one, so a bare
`docker compose up` starts nothing; the frontend is in `dpasp` and `mock`.

#### `Blocked request. This host ("…") is not allowed.`

Vite's development server answers only to hostnames it recognises —
`localhost`, `*.localhost` and bare IP addresses by default. Reach it by any
other name and it returns 403 with that message.

It is a defence against DNS rebinding: without it, a page on an attacker's
domain whose name resolves to 127.0.0.1 could read from a dev server running
on the visitor's machine. So the fix is to name the hosts the deployment
answers to, not to switch the check off:

```
# .env, next to compose.yaml
DPASP_ALLOWED_HOSTS=kamel.ime.usp.br
```

A leading dot covers a domain and every subdomain — `.ime.usp.br` allows
`kamel.ime.usp.br`. Several names are comma-separated. The literal `true`
disables the check, which is worth using only when something in front of the
app already controls which hosts reach it.

Measured behaviour, so the shape of the thing is clear: with the variable
unset, `Host: kamel.ime.usp.br` gets 403 and `localhost` gets 200; set to
`kamel.ime.usp.br` or `.ime.usp.br`, that host gets 200 while
`Host: evil.example.com` still gets 403; set to `true`, everything gets 200.

The better answer for a machine on a network is not to run the dev server at
all — see **On a server** above. The built target has no host check because
it does not need one.

#### `Cannot find base config file "./.svelte-kit/tsconfig.json"`

Printed by esbuild, from `editor/tsconfig.json`, whose first line is
`"extends": "./.svelte-kit/tsconfig.json"`. That parent config is **generated**
by `svelte-kit sync` and is not in git, so on a fresh checkout it does not
exist yet and esbuild reads the file before SvelteKit's Vite plugin has run
sync. The build then succeeds anyway, using esbuild's defaults for that first
pass instead of the project's compiler options.

This is why it showed up on a new computer and nowhere else: on a machine
where the editor has ever been built, `editor/.svelte-kit/` is already there,
and the dev container mounts `./editor` from the host, so it inherits whatever
the host has.

Fixed by running sync explicitly rather than hoping something else has:
`dev`, `build`, `check` and `test` in `editor/package.json` all begin with
`svelte-kit sync`, and a `prepare` script runs it on `npm ci`/`npm install`
for editors and type-checkers that look at the project before any script runs.
`editor/Dockerfile` copies `svelte.config.js` into the install layer so that
`prepare` has what it needs there too — sync reads the config but not `src/`,
and without the config it prints `Missing /app/svelte.config.js — skipping`
into every image build.

If you see it again, run `npm run check` (or any of the others) once in
`web/editor`, or `npx svelte-kit sync`.

#### The editor says it cannot obtain a runner, or the log shows `ECONNREFUSED`

On a cold start the first **image build** is the slow part — several minutes,
since it compiles dPASP against clingo and downloads PyTorch. That build is
Compose's, so it happens before anything starts and you watch it in the `up`
output. The manager's own warmup afterwards takes seconds:

```bash
curl localhost:8001/health     # {"status":"starting"|"ready"|"error"}
docker compose logs -f container-manager
```

The manager still does its Docker work in a background task rather than in
uvicorn's lifespan. Uvicorn binds its listening socket only after the
lifespan's startup block returns, so anything slow inline there makes the
whole API refuse connections — which the frontend logged as

```
container-manager lookup failed: TypeError: fetch failed
  [cause]: Error: connect ECONNREFUSED 172.18.0.3:80
```

saying nothing about the real cause. Detached, the API answers immediately and
returns `503` with an explanation the editor displays. (The build used to live
there too, which is what made that window minutes long rather than seconds.)

If `/health` reports `"status": "error"`, `detail` carries the reason. The
most likely one now is that the runner image was never built:

```
The runner image 'dpasp-runner' does not exist. Compose builds it as the
`runner-image` service …
```

which means the stack was started without a profile, or with a Compose file
that predates that service.

#### `runner-image-1 exited with code 0`

Expected, and the point of that service. `runner-image` exists so that
**Compose** builds the runner image; the manager is no longer allowed to.
Since a Compose service that builds an image also gets a container, its
`entrypoint` is overridden with an echo and it exits at once — the container
manager waits for exactly that, with `condition: service_completed_
successfully`, so the image is guaranteed to exist before it looks for it.

A runner container that actually served here would be the bug: unmanaged,
unbounded, and on the wrong network. The override is runtime only; the image
keeps its own `CMD`, which is what the real runners run.

#### `InvalidArgumentError: invalid onRequestStart method`

```
frontend-1 | proxying blob/list failed: [TypeError: fetch failed] {
frontend-1 |   [cause]: InvalidArgumentError: invalid onRequestStart method
frontend-1 |       at assertRequestHandler (/app/node_modules/undici/lib/core/util.js:573:11)
frontend-1 |     code: 'UND_ERR_INVALID_ARG'
```

**Two copies of undici, disagreeing.** Node's global `fetch` *is* undici — a
copy bundled inside Node — and `runnerFetch` was handing it a `dispatcher`
built from the `undici` package in `node_modules`. Node's fetch constructs a
request handler shaped for its bundled version and passes it to that
dispatcher, which validates it and refuses. The two shapes agreed for long
enough to look like one library, and stopped agreeing at undici 8.

Nothing about it is visible to the type checker: both `fetch`es have the same
signature, and the failure is at the first request, not at build time.

The fix is to stop mixing them — take the `fetch` from the same package as the
`Agent`:

```ts
import { Agent, fetch as undiciFetch } from 'undici';
```

so nothing depends on which undici the Node image happens to bundle.
`src/lib/runnerFetch.test.ts` pins it by calling a real `http.createServer`;
reverting the import makes three of its tests fail with exactly the error
above.

#### `getaddrinfo ENOTFOUND dpasp-instance-<id>`

The frontend logs this when it proxies a request to a runner:

```
frontend-1 | proxying blob/list failed: TypeError: fetch failed
  [cause]: Error: getaddrinfo ENOTFOUND dpasp-instance-92c0fb801811
```

Docker's embedded DNS only answers for containers that are *running*, so the
name disappearing means the container is gone or stopped — not that the
network is misconfigured. Two things produce it.

**The runner died.** Ask its own log why, and check whether it is still
listed:

```bash
docker ps -a --filter label=dpasp.role=runner
docker logs dpasp-instance-<id>
```

A runner that fails to start is now refused at creation rather than handed
out: `createContainer` waits for `running`, waits `DPASP_RUNNER_START_GRACE`
(0.75 s by default) for a container that exits immediately after starting,
re-checks, and on failure raises with the container's last 20 lines of output
before removing it. `getContainer` re-checks liveness before handing out a
pooled or previously assigned container, so a runner that died while idle is
replaced instead of returned. What remains is a runner that dies *after* it
was handed out — that is what the message above now says, with the two
commands to run.

**Two networks match the name.** `docker.networks.list(names=…)` matches on a
substring, so a second network whose name merely *contains* `dpasp-instances`
(one created by hand, or a second Compose project) makes the choice ambiguous:
the runner can land on a network the container manager is not attached to, and
the name then never resolves. Check with

```bash
docker network ls | grep dpasp-instances
```

The manager now disambiguates by reading its own Compose labels
(`com.docker.compose.project` / `.network`, via its container's hostname), and
raises with the list of candidates if it still cannot decide. To settle it
explicitly, name the network:

```bash
# .env, next to compose.yaml
DPASP_RUNNER_NETWORK=web_dpasp-instances
```

Reloading the page asks the manager for a fresh container either way.

#### `PermissionError: [Errno 13] Permission denied: '/app/main.py'`

Reported through `/health` as the runner exiting on startup:

```json
{"status":"error","detail":"RuntimeError: The runner container … is exited
 (exit code 1) … PermissionError: [Errno 13] Permission denied: '/app/main.py'"}
```

uvicorn raises it while importing `main:app`, so the container dies at once.
The cause is not in the runner code: **`COPY` preserves the mode bits of the
files in the build context**, and those come from the umask your checkout was
made with. Under the usual 022 they are 0644 and all is well; under 077 they
land in the image as 0600 owned by root. That was invisible while the server
ran as root — root ignores permission bits — and became fatal the moment it
stopped.

```bash
ls -l backend/dPaspRunner/main.py      # 0600 on the build host?
```

The image no longer depends on the answer: both stages run
`chmod -R a+rX /app` after their last `COPY`, and the dpasp stage then reads
`/app/main.py` as `runner` so a broken build fails at `docker build` rather
than at a visitor's first query. `backend/dPaspRunner/test_dockerfile.py`
keeps both in place without needing a daemon.

The runner image is the `runner-image` Compose service, built straight from
`backend/dPaspRunner`, so `up --build` picks the fix up:

```bash
docker compose --profile dpasp down
docker ps -aq --filter label=dpasp.role=runner | xargs -r docker rm -f
docker compose --profile dpasp up --build
```

`down` first because the manager caches its startup error for the life of the
process: rebuilding the image under a running manager changes nothing.

(This used to be worse. The manager built the image itself, from a *copy* of
`backend/dPaspRunner` baked into its own image, so the mode bits travelled
host → manager image → runner image and both had to be rebuilt. Moving the
build to Compose removed that hop along with the build capability.)

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

### On a server

The `dpasp` profile runs **Vite's development server**, which is not
something to leave facing a network: it serves the source tree, watches the
filesystem, and has to be told which hostnames it may answer to. Use the
`dpasp-prod` profile instead. It builds the app with `@sveltejs/adapter-node`
and serves it with `node build` — no Vite at run time.

```bash
cd web
cp .env.example .env         # then edit; see below
docker compose --profile dpasp-prod up -d --build
```

The minimum for a host called `kamel.ime.usp.br`, answering on port 8000 over
plain HTTP:

```
DPASP_ORIGIN=http://kamel.ime.usp.br:8000
DPASP_RESTART=unless-stopped
```

`DPASP_ORIGIN` is the URL users type. Without it the server assumes `https://`
and takes the host from the request header, which makes generated links and
OAuth callbacks point somewhere that does not exist. `DPASP_RESTART` brings
the stack back after a reboot. `.env.example` documents the rest: the port,
the upload size limit, the runner's time and memory limits, and the OAuth
credentials that turn on sign-in.

Behind a reverse proxy that terminates TLS, leave `DPASP_ORIGIN` empty and
let the app read the forwarded headers instead:

```
DPASP_PROTOCOL_HEADER=x-forwarded-proto
DPASP_HOST_HEADER=x-forwarded-host
```

Two things to know about this target:

- **Uploads are capped at 32 MB** (`DPASP_BODY_SIZE_LIMIT`, in bytes). The
  editor posts a file as one JSON body, and adapter-node's own default would
  be 512 kB — with that, any upload much over half a megabyte comes back as
  `413 Invalid request body`. The limit is raised in `compose.yaml`; raise it
  further for larger data files.
- **Runner containers are bounded, not root, and have no route out** — see
  *What bounds a runner* for the numbers and *What bounds the container
  manager* for what the web tier can ask the daemon to do. On a shared machine
  the defaults are the interesting ones: 1 CPU and 3g per runner, and no
  internet unless `DPASP_RUNNER_ALLOW_NETWORK=1`.

#### Stopping it

```bash
cd web
docker compose --profile dpasp-prod down                          # 1
docker rm -f $(docker ps -aq --filter label=dpasp.role=runner)    # 2
```

Both lines are needed, for different reasons.

**1. The profile has to be repeated.** Compose only acts on services whose
profiles are active, so a bare `docker compose down` stops *nothing* here —
every service in this file belongs to a profile. The same goes for `ps`,
`logs` and `stop`. `COMPOSE_PROFILES=dpasp-prod` in the `.env` is the
alternative, and then the flag can be left off every command.

**2. The runner containers are not Compose's.** The container manager creates
them through the Docker API, so `down` leaves them running; they are labelled
`dpasp.role=runner`, which is what the filter above matches. The manager
sweeps leftovers when it next starts, so they are not permanent — but between
a `down` and the next `up` they keep running, holding memory and a network
endpoint.

That endpoint is why the order matters. `down` tries to remove the
`dpasp-instances` network, and a network with containers still attached
cannot be removed; if `down` reports that, run it once more after line 2 to
clear the network. Leaving a removed network referenced by live containers is
what produced `failed to set up container networking: network <id> not found`
on the next start.

To check that nothing is left:

```bash
docker compose --profile dpasp-prod ps
docker ps --filter label=dpasp.role=runner
```

Other useful forms:

| | |
| --- | --- |
| `docker compose --profile dpasp-prod stop` | stop without removing; `start` resumes. Survives a reboot as stopped, since `restart: unless-stopped` does not restart what a person stopped |
| `docker compose --profile dpasp-prod restart frontend-prod` | bounce one service |
| `docker compose --profile dpasp-prod logs -f frontend-prod` | follow its log |
| `docker compose --profile dpasp-prod down -v` | also drop the named volume, which only the dev profile uses |

Development is unchanged — `docker compose --profile dpasp up --build` still
runs the dev server with hot reload. The one difference is that the frontend
now belongs to the `dpasp` and `mock` profiles rather than starting for every
command, so a bare `docker compose up` with no profile no longer starts it.

If you do want the dev server reachable by name — for a quick demo on a
trusted network, say — name the host rather than disabling the check:

```
DPASP_ALLOWED_HOSTS=kamel.ime.usp.br
```

See the troubleshooting entry below for what that check is for.

## The runner's result format

`POST /run` takes `{code}` and always answers `200` with a body of this
shape. A faulty program is not an HTTP error: it comes back with
`ok: false` and a structured `error`, so the editor renders it in the output
panel like any other outcome.

```json
{
  "ok": true,
  "sem": "stable",
  "psem": "credal",
  "interval": true,
  "learned": false,
  "instances": 1,
  "instances_shown": 1,
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
- `instances` is 1 for an ordinary program. A program with neural rules
  answers every query **once per row of its test data**, and then `queries`
  holds that many blocks of one entry per `#query`, each entry tagged with
  its 0-based `instance`. `instances_shown` is smaller than `instances` when
  the test set exceeded `DPASP_MAX_RESULT_INSTANCES` (50). See "The extra
  dimension a neural program adds" below.
- `sem` and `psem` are **reported, not requested**. The request body is just
  `{code}`: dPASP decides the semantics from the program's own `#semantics`
  directive, and the runner reads both halves back off the parsed program —
  `program.semantics` for the logic one, `directives["psemantics"]` for the
  probabilistic one, which is credal when the program says nothing.
- Non-finite bounds are sent as the strings `"inf"`, `"-inf"` and `"nan"`,
  because JSON has no literals for them and `JSON.parse` rejects the
  alternatives.
- `output` is only what the program itself printed. dPASP's progress bar and
  its import-time notices are stripped.
- `error.kind` is one of `parse`, `runtime`, `timeout`, `internal`. Parse
  errors carry `line` and `column`.

### The extra dimension a neural program adds

dPASP's result array does not have one shape. In `exact.c`, just before the
`PyArray_SimpleNewFromData` call:

```c
if (has_neural) { nd = 3; dims[0] = p.m_test; dims[1] = p.Q_n; dims[2] = ...; }
else            { nd = 2; dims[0] = p.Q_n;    dims[1] = ...; }
```

So an ordinary program returns `(n_queries, n_values)` and a program with
neural rules or neural annotated disjunctions returns
`(n_test_instances, n_queries, n_values)`, where the last dimension is 2 under
credal semantics and 1 under max-entropy. `m_test` is the number of rows the
`test(...)` data carries, and dPASP prints one block of answers per row,
separated by `---`.

The runner used to read every result as the 2-D shape, and that is a quiet,
plausible kind of wrong: iterating a 3-D array yields *blocks*, not rows, so
`poisson.pasp` — which asks two queries and gets one probability for each —
came back as **one** query holding two values, and the panel showed

    ℙ(disaster) = [0.147152, 0.001037]

with the second query's probability presented as the first query's upper
bound. Nothing errored; the numbers were even right. Only their labels were
wrong, which is the failure mode that survives a smoke test.

`runner_worker.as_instances` now normalises both shapes to a list of blocks,
`array_depth` reads `ndim` when there is one and falls back to counting
nesting (so the shaping can be tested with plain lists), `interval` is read
off a **query row** rather than the outermost dimension, and entries carry
an `instance` index only when there is more than one block.

Two consequences worth knowing:

- Adding a `#query` to a neural program adds a row to every block, not a
  block. Adding a row of test data adds a block.
- A real test set is large, so the payload is capped at
  `DPASP_MAX_RESULT_INSTANCES` blocks (50) and the response says how many
  there were. dPASP's own printer stops far sooner — `cexact.c` sets
  `quiet = quiet || (data_stride > 10)`.

Verified against real dPASP with PyTorch, not against a fixture: `poisson.pasp`
reports ℙ(disaster) = 0.147152 and ℙ(joint) = 0.001037 as two entries with one
value each; the same program with three rows of test data reports six entries
across three blocks whose probabilities fall as the Poisson counts grow; the
same again without `#semantics maxent.` reports bounds; and the truncation cap
was checked by setting `DPASP_MAX_RESULT_INSTANCES=2` against a five-row run.
In Chromium, against the production bundle and a real runner, the panel shows
`Query | Probability` for the one-block case and `Row | Query | Probability`
with a hairline between blocks for the three-block case, and `insomnia.pasp`
still shows `Query | Lower | Upper`.

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

Tunable through the environment: `DPASP_RUN_TIMEOUT` (default 300 s),
`DPASP_RUN_MEM_MB` (default 1024), `DPASP_MAX_OUTPUT` (default 65536 chars),
`DPASP_MAX_RESULT_INSTANCES` (default 50).
These sit inside the runner container and complement, not replace, whatever
CPU and memory limits the container itself is given.

Runner containers are created through the Docker API, not by Compose, so
nothing would otherwise give them an environment — these three are forwarded
from the container manager (`containerManager.RUNNER_ENV_KEYS`), which Compose
passes them to. Override in a `.env` file next to `compose.yaml`:

```
DPASP_RUN_TIMEOUT=600
```

and restart. Only those three are forwarded; the container manager's own
environment is not handed to containers that run user programs.

A long deadline means the HTTP connection is held open for the whole run, so
the proxy in front of the runner has to be willing to wait at least as long.
Node's `fetch` is undici, whose `headersTimeout` defaults to **300 s** — the
same as the run limit — so the two would race and a slow run could fail with
`UND_ERR_HEADERS_TIMEOUT` instead of the runner's own timeout message.
`editor/src/lib/runnerFetch.ts` therefore sets that timeout explicitly, 30 s
above the run limit (`DPASP_PROXY_TIMEOUT_MS`, default 330000). If you raise
`DPASP_RUN_TIMEOUT` past 300 s, raise this too.

`DPASP_RUN_MEM_MB` bounds the **heap** (`RLIMIT_DATA`), deliberately not the
address space (`RLIMIT_AS`), and it is applied **after** the worker has
imported dPASP, as a budget on top of what that import costs. Both halves of
that sentence are the result of a failure in production, and both show up the
same way — as the dynamic loader failing to map a segment.

`RLIMIT_AS` counts file-backed mappings, and importing PyTorch maps far more
address space than it ever uses: measured here, `import pasp` with the CUDA
build peaks at 3.2 GB of address space while holding 788 MB of data mappings.
Capping the address space therefore made the loader's `mmap` fail and every
run die with `libtorch_python.so: failed to map segment from shared object`.

`RLIMIT_DATA` exempts those mappings — but applying it *before* the imports
still put the loader inside the user's budget. That budget is not generous
next to the CUDA build of torch, which needs ~790 MB of it just to import, so
on x86_64 hosts the import itself hit the ceiling and died with
`libc10_cuda.so: failed to map segment from shared object`. Our own runtime
loading itself is not what the limit is for, so it is now applied afterwards:

```python
apply_process_limits()          # core dumps, stack — harmless to the loader
import pasp                     # whatever it needs, it gets
apply_memory_limit(budget_mb)   # RLIMIT_DATA = VmData + budget
```

`DPASP_RUN_MEM_MB` is therefore what a *program* may allocate, not what the
process may total. A runaway allocation still fails, cleanly, as a
`MemoryError`. If a legitimate program needs more than 1 GB, raise the
variable rather than reaching for `RLIMIT_AS`.

The runner image installs **CPU-only** torch for the same reason, and because
runner containers are created without `--gpus`: `torch.cuda.is_available()` is
False whatever is installed, while the CUDA wheels cost about 4 GB of image
and ~700 MB of data mappings. Build with
`--build-arg TORCH_INDEX=https://pypi.org/simple` to get the default PyPI
wheel back; the build falls back to it automatically if the CPU index has no
wheel for the platform, and the runner works with either.

## What bounds a runner

A dPASP program may contain a `#python ... #end.` block, and dPASP executes
it. So a runner container runs arbitrary Python chosen by whoever opened the
page: **the container is the security boundary, not the code inside it.** The
per-run timeout and heap rlimit of the previous section bound one *program*;
nothing there stops it from spawning processes, filling a disk or opening a
socket.

`containerManager.runnerLimits` is what bounds the container. Every value has
an environment override — `.env.example` lists them — and the manager prints
the effective set when it starts.

| | default | why |
| --- | --- | --- |
| `nano_cpus` | 1.0 core (`DPASP_RUNNER_CPUS`) | a hard quota, not a share: one user's grounding cannot slow everyone else's |
| `mem_limit`, `memswap_limit` | 3g (`DPASP_RUNNER_MEM`), equal, so no swap | must cover ~800 MB to load dPASP, `DPASP_RUN_MEM_MB` of program heap, and the tmpfs below |
| `pids_limit` | 256 (`DPASP_RUNNER_PIDS`) | a fork bomb exhausts its own container and nothing else |
| `user` | `10001:10001` | the image ends with `USER runner`; this is the half that survives an edit to the image, and the only part Docker compares |
| `cap_drop` | `ALL`, nothing added back | the runner listens on **8000**, not 80, precisely so that binding it needs no `NET_BIND_SERVICE` |
| `security_opt` | `no-new-privileges:true` | no regaining privileges through a setuid binary |
| `read_only` | true (`DPASP_RUNNER_READONLY=0` to disable) | with tmpfs for `/tmp` (the worker's result file) and `/blobs` (uploads), both `nosuid,nodev`, and `/blobs` `noexec` |
| `ulimits` | 1024 open files | |
| network | the internal `dpasp-instances` only | no route off the host — see below |
| `OMP_NUM_THREADS` etc. | the CPU quota | PyTorch and OpenMP size their pools from the *host's* CPU count, so under a 1-core quota they would start a dozen threads to contend for one core |

### No route out

Two things together do this, and both are needed:

1. `compose.yaml` declares `dpasp-instances` as `internal: true`. Docker gives
   an internal network no gateway, so a container attached only to it cannot
   reach the host's network, let alone the internet.
2. The manager passes `network=` to `containers.run`, so the container is
   *created* on that network. This is the part that is easy to miss: a
   container Docker attaches by default lands on the default bridge, which is
   masqueraded. Attaching the runner network afterwards — which is what the
   code used to do, to add an alias — leaves the default bridge in place and
   the internet with it.

Because `containers.run` takes `network=` but not `aliases=`, runners are now
*named* `dpasp-instance-<id>` rather than given that as an alias. Docker's
embedded DNS resolves container names on a user-defined network, so
`http://dpasp-instance-<id>` still resolves from the frontend and nothing in
the editor changed.

The frontend is on `dpasp-instances` too, so it can reach runners, and on
`cm` as well. A container on both keeps its default route and its published
ports on the non-internal one, so publishing port 8000 is unaffected.

To let programs reach the internet again:

```
DPASP_RUNNER_ALLOW_NETWORK=1
```

The manager then also attaches the default bridge to each runner. One shipped
example still needs it: `learning.pasp` reads its CSV from a URL. Uploading
the CSV and referring to it by name works either way, which is why the
example's comments recommend it. (`digitsum.pasp` used to need it too; MNIST
is cached in the runner image now — see *The MNIST cache* below.)

### Not root

The image creates a `runner` account (uid and gid **10001**) and ends with
`USER runner`; the manager passes `user="10001:10001"` as well, which is the
half that survives someone editing the image and is the only part Docker
compares. 10001 rather than 1000 because distributions hand 1000 out
themselves — `ubuntu:jammy` leaves it free, but `ubuntu:24.04` ships a user
holding it, so a base-image bump would fail with "UID 1000 is not unique". Everything the image needs to read is world-readable, and the two
paths the server writes to are mounted at run time.

This is why the runner listens on **8000** rather than 80: binding below 1024
needs `CAP_NET_BIND_SERVICE`, and the point is to hold no capabilities at
all. The port appears in `backend/dPaspRunner/Dockerfile` and in
`editor/src/lib/runnerUrl.ts`; a test reads the Dockerfile and fails if the
two disagree, since a mismatch would otherwise show up only once deployed, as
every run reporting an unreachable runner.

### Measured against a real daemon

All of the above was checked by creating a runner with the real
`containerManager` code against a real Docker daemon, and inspecting what
came out:

```
user 10001:10001 | nano_cpus 1000000000 | memory 3221225472 | memswap 3221225472
pids 256 | read_only true | cap_drop [ALL] | cap_add <no value>
security_opt [no-new-privileges:true] | ulimits [nofile 1024/2048]
tmpfs {"/blobs":"size=256m,mode=1777,noexec,nosuid,nodev",
       "/tmp":"size=64m,mode=1777,nosuid,nodev"}
networks ["web_dpasp-instances"]
```

and from inside it:

- `id` → `uid=10001(runner) gid=10001(runner)`, and `CapEff: 0000000000000000`
  — an empty capability set, not merely a reduced one;
- `touch /nope` → `Read-only file system`; `/tmp` and `/blobs` writable;
- the cgroup agrees: `cpu.max 100000`, `memory.max 3221225472`,
  `pids.max 256`;
- writing 300 MB into `/blobs` stops at 256 MiB, and `/tmp` at 64 MiB;
- **`/proc/net/route` is empty — no default route at all**, and a TCP connect
  out fails with `Network is unreachable`. With
  `DPASP_RUNNER_ALLOW_NETWORK=1` the same container gains `eth1` and a
  default route, which is the difference that variable is supposed to make;
- from a *peer* container on the same internal network — the frontend's
  position — `dpasp-instance-<id>` resolves, `POST /blob/list` answers, and a
  real query returns ℙ(burglary | alarm) = 0.8333.

`deleteContainer` removes the container; `removeStaleContainers` sweeps by
label. A container attached to both `dpasp-instances` (internal) and `cm`
publishes its port normally — checked in both attachment orders, since that
is what the frontend depends on.

The same setup was used to check that a runner which *fails* is not handed
out. Against an image whose command exits immediately, `createContainer`
answers

```
The runner container 0a6f71c46b21 is exited (exit code 3) instead of running,
so it was removed rather than handed out. Its last output was:
  | uvicorn: error: could not start
```

and leaves nothing behind. The first version of that check passed a dying
container as healthy: a container that exits ~50 ms after `start()` still
reads `running` on the first `reload()`, so the wait succeeded before the
process had failed. Hence `DPASP_RUNNER_START_GRACE` — wait, re-check, and
only then hand it over. Killing pooled containers behind the manager's back
and asking for one confirms the other half: the dead ones are skipped and the
container that comes back is `running`.

The one thing that could not be checked is **building the images**: the
container registry is blocked by egress policy from this environment
(`registry-1.docker.io` answers 403 to CONNECT), so `ubuntu:jammy` and
`node:20-alpine` cannot be pulled. The runner used above was a stand-in image
whose final stage is identical to the real one — same `useradd`, same
`/blobs` ownership, same `USER`, same port, same `CMD` — built on a base
imported from the test machine's own filesystem.

### What this does not do

Nothing here limits disk I/O bandwidth or the number of containers a single
visitor can cause to be created; `pruneContainers` exists for the latter but
nothing calls it.

## What bounds the container manager

Bounding the runners left the *manager* as the softest thing in the stack. It
created them through the Docker API, which meant `/var/run/docker.sock` was
mounted into it — and that socket is root on the host. Anything able to reach
it can ask for

```json
{"Image": "alpine", "HostConfig": {"Binds": ["/:/host"], "Privileged": true}}
```

and walk out onto the machine. Every limit in the section above is downstream
of a process that could have skipped all of them.

So the socket now lives in its own container. `docker-proxy`
(`backend/dockerProxy/`) holds it and listens on an internal network that
only the manager is attached to; the manager gets
`DOCKER_HOST=tcp://docker-proxy:2375`. **The manager's own code did not
change** — `docker.from_env()` reads that variable — which is the point: it
makes the same calls, and the ones it should never have been able to make now
fail with 403 instead of succeeding.

`backend/dockerProxy/policy.py` is the entire policy, as one pure function of
one HTTP request. Three kinds of rule:

- **An allowlist.** `POST /containers/{id}/exec`, `GET /secrets`,
  `POST /swarm/init`, `PUT /containers/{id}/archive` and several hundred
  others are refused because they were never listed — not because anyone
  thought to deny them.
- **Forcing, not checking.** On `POST /containers/create` the dangerous
  fields are *overwritten*. A validator is only as good as its author's
  imagination; an overwrite does not care what was asked for. `Privileged` is
  false because the proxy makes it false — likewise `Binds`, `Mounts`,
  `VolumesFrom`, `Devices`, `CapAdd`, `SecurityOpt`, every `*Mode` namespace
  field, `Sysctls`, `PortBindings`, `CgroupParent`, `Runtime`, and the
  `MaskedPaths`/`ReadonlyPaths` that hide `/proc/kcore` (set to `null`, since
  an empty list *unmasks* them). The image must be `dpasp-runner`, the name
  must be `dpasp-instance-<id>`, the network must be the runner network, and
  `User` is forced to 10001 — a third independent place, after the image's
  `USER runner` and the manager's `user=`.
- **Ownership.** Anything naming an existing container — inspect, logs, stop,
  start, remove, network connect — is allowed only once the proxy has asked
  the daemon whether that container carries `dpasp.role=runner`. Otherwise a
  compromised manager could read the frontend's environment, which is where
  `AUTH_SECRET` and the OAuth secrets live. Container *listing* has its label
  filter forced, so a list cannot return anything else either.

The one exception to ownership is that the manager may inspect **itself**:
it reads its own Compose labels to resolve an ambiguous runner network. The
proxy recognises it by comparing Compose project and service against its own
labels, so a manager from a different stack on the same daemon is refused.

The proxy is stdlib-only and installs nothing — the most privileged container
in the stack has no dependency to audit — and Compose gives it `read_only`,
`cap_drop: ALL`, `no-new-privileges` and a 64-process limit. It publishes no
port: exposing it would hand the host's daemon to the network, a worse hole
than the one it closes.

### What is left

A compromised manager can create, inspect and destroy *runners* — bounded
ones, on an internal network, as uid 10001 — and nothing else.

In particular it can no longer make the daemon **execute** anything of its
choosing. `POST /build` was the last such primitive: a build runs a Dockerfile,
which means `RUN` steps as root in a build container. It was on the allowlist
only because the manager built the runner image at startup. Compose builds it
now, as the `runner-image` service, so `ensureImage` does a lookup where there
used to be a build, `/build` is off the allowlist entirely, and the manager's
image no longer even carries a copy of `backend/dPaspRunner` to build from.

The remaining calls are all *about containers we made*: create (rewritten),
start, stop, remove, inspect, logs, and a network connect. Image endpoints are
read-only — no create, no pull, no tag, no load, no commit, no prune.

### Tested without a daemon

`backend/dockerProxy/` has 49 tests and none of them need Docker. The policy
is a pure function, so the escapes are asserted directly — "the request that
reaches the daemon has `Privileged: false`", not "the request was rejected".
Above that sits a fake daemon on a unix socket with the real proxy in front
of it, driven by a real `docker-py` client, and
`test_manager_through_proxy.py` drives the **real** `containerManager` module
through the whole chain: it creates, inspects, sweeps and deletes as it
normally does, and then tries to mount the host and is refused.

The policy tests were checked against mutation: deleting the `Privileged`
override, the `CapDrop`, the forced build tag, the network check or the
forced list filter each makes exactly one test fail, by name.

## Semantics come from the program

There are no semantics controls in the toolbar. A program says which
semantics it wants, in its own text:

```prolog
#semantics maxent.              % probabilistic: credal (default) or maxent
#semantics lstable.             % logic: stable (default), partial, lstable, smproblog
#semantics lstable, maxent.     % both
```

This is not only a matter of taste. dPASP's parser pre-scans the source for
the directive and lets it override whatever the caller passed
(`PreparsingTransformer` in `pasp/grammar.py`), so the dropdowns that used to
sit in the toolbar were a second and weaker source of truth: open a program
containing `#semantics maxent.`, leave the dropdown on "credal", and the
toolbar would say credal while the run used max-entropy.

So `POST /run` now takes `{code}` and nothing else, and the two pills in the
output panel's header **report** what dPASP used — read back from the parsed
program, not echoed from the request. Change the directive, run again, and
the pills change with it; the query table switches between a bounds pair and
a single probability at the same time.

### Downloading a program

The download button in the toolbar saves the open file to your machine, under
its own name. It saves the buffer — including edits you have not run yet —
with one exception: a file open as a **prefix** (see the line limit below) is
fetched whole from the runner first, because handing someone a silently
truncated copy of their own data file is worse than making them wait a
moment. `planDownload` in `editor/src/lib/download.ts` is that decision, and
it has tests.

## The file list

Two buttons: **New file** and **Upload a data file**. There used to be a third,
*List files*, which fetched the file names and printed them into the output
panel's notice line — the same names the panel beside it was already showing.

Entries are drawn with the glyph their extension earns:

| extension | glyph | |
| --- | --- | --- |
| `.pasp`, `.plp`, `.lp`, `.pl` | a solid document | a dPASP program: open it, run it |
| `.csv`, `.tsv` | an outlined table | a data file: referenced by name from `#learn` or a `#python` block, not run |
| anything else | a solid document | no guess |

`fileGlyph` in `src/lib/ui/icons/paths.ts` is that mapping, and it is a pure
function with its own tests — including that the two glyphs stay *distinct*,
since returning the same path for both would satisfy every other assertion.
The extension is matched case-insensitively (`DATA.CSV` comes off a user's
machine looking like that) and only at the end of the name, so `csv-notes.pasp`
is a program.

Each icon carries its kind as an accessible label, so a screen reader reads
"dPASP program earthquake.pasp" rather than the filename alone.

Names are white; the **open** file is named in the accent
(`--color-primary-500`, the same pink as "dPASP Playground" in the title bar),
and its icon follows, since `Icon.svelte` draws in `currentColor`. One pink
thing on screen, and it is always "where you are".

The selected row is *recessed* rather than lightened, which is the part worth
knowing: selection used to be a lighter `#3a3a3a`, and the accent on that
measures 4.39:1 — under the 4.5:1 AA floor for 13 px text. Darkening the row
to `#262626` takes the same colour to 5.84:1, so the file you are editing is
the most readable line in the list rather than the least.

## Files, and the editor's line limit

Uploaded files land in the runner's blob folder, which is the working
directory of every run, and appear in the panel on the left. A program can
therefore read one by its bare name — `#learn "elmo.csv"`, or `open("x.csv")`
inside a `#python` block.

Data files are routinely far larger than anything a text editor should try to
show, so **the editor opens at most 1000 lines** (`MAX_EDITOR_LINES` in
`editor/src/lib/limits.ts`). `POST /blob/fetch` takes an optional `max_lines`
and answers with the counts, so the cut is made in the runner rather than by
sending megabytes of CSV to the browser first:

```json
{ "content": "…first 1000 lines…", "truncated": true,
  "total_lines": 5001, "shown_lines": 1000, "bytes": 20025 }
```

A file opened this way is a **prefix**, and the editor treats it as one:

- a banner above the buffer says how much is shown, of how much;
- the editor is read-only, and nothing writes the buffer back — saving a
  prefix over the file would delete everything past the cut, silently, which
  for a data file means all of it;
- the run button is disabled, because running the first 1000 lines of a
  program is not running that program;
- the whole file is still on the server and still read in full by any program
  that opens it. That is the point of the banner's last sentence: truncation
  is a display limit, not a data limit.

An upload of more than 1000 lines says so as it lands, rather than waiting
for the user to open the file and wonder.

Omitting `max_lines` returns the file whole, which is what any other client
of the endpoint gets.

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

## Example programs

The "New file" dialog offers a **Start from** dropdown seeded with eight
programs, so a newcomer can run something real without typing it first:

| File | Shows |
| --- | --- |
| `earthquake.pasp` | probabilistic facts and rules, conditional queries |
| `insomnia.pasp` | the smallest program with non-degenerate credal bounds |
| `coloring.pasp` | L-stable semantics and `undef` queries |
| `prisoners.pasp` | interval-valued (credal) facts |
| `argumentation.pasp` | probabilistic rules that attack and support each other, with the two halves of the semantics declared one directive each |
| `learning.pasp` | learnable facts (`?::`) fitted to a CSV with `#learn` |
| `poisson.pasp` | a **PyTorch** module supplying probabilities: a `#python` block and a neural annotated disjunction, `!::event(X) as @Poisson` |
| `digitsum.pasp` | `#python` blocks, neural rules and `#learn`, on MNIST |

The sources live in `editor/src/lib/examples/` as ordinary `.pasp` files and
are pulled in with Vite's `?raw`, rather than pasted into a TypeScript
literal. That keeps them readable and editable. All but `learning.pasp` and
`digitsum.pasp` are currently byte-identical to their counterparts in the
dPASP repository's own `examples/` directory — `coloring.pasp` is
`3coloring.plp`, renamed only to match what the dialog calls them. Diff them
against upstream when dPASP changes. `digitsum.pasp` is `add_mnist.plp` with
its data loading changed (see below); `learning.pasp`
comes from the [parameter-learning
tutorial](https://kamel-usp.github.io/pages/learn_dpasp.html#learning-the-parameters-of-programs)
and carries added comments.

All but two run in about a second and reproduce their published figures —
checked here against real dPASP: `argumentation.pasp` in 1.8 s, and
`poisson.pasp` giving ℙ(disaster) = 0.1472 and ℙ(joint) = 0.0010, which are
the numbers its own comments predict. The other two are called out in the
dialog when selected, rather than being left to look broken:

* `learning.pasp` takes roughly 15 seconds and reads its CSV from a URL.
  dPASP resolves that URL **while the program is parsed** (`path2obs` in
  `pasp/grammar.py` calls `pandas.read_csv`), so an unreachable host fails
  the run before any inference happens, and the runner needs outbound
  network as long as the URL is left in place. The program's own comments
  point at the better route: upload a copy with the file browser's upload
  button and replace the URL with the bare file name, since programs run
  with the uploaded-files folder as their working directory. That is also
  what will keep working once the runner is network-isolated (see *Known
  gaps*).
* `digitsum.pasp` trains a convolutional network on all 60000 MNIST images.
  That takes about 45 seconds on one CPU — comfortably inside the 5-minute
  deadline, but long enough that the dialog should say so. It also returns 95
  rows, for the reason in *The MNIST cache*.

### The MNIST cache

`digitsum.pasp` is the one example whose data does not fit in the file. As
published it calls

```python
torchvision.datasets.MNIST(root = "/tmp", train = True, download = True)
```

and neither half of that can work in a runner:

- **torchvision is not installed.** It is a large wheel with its own torch
  version constraint, brought in to fetch four files and decode a format that
  `gzip` and `struct` handle in eight lines.
- **A runner has no route off the host.** `dpasp-instances` is internal and
  `DPASP_RUNNER_ALLOW_NETWORK` is 0 by default, so the download does not fail
  quickly or informatively. The root filesystem is read-only besides, so
  `root = "/tmp"` would land on the tmpfs and every user would pay for the
  download again, inside their own 5-minute deadline.

So the runner image carries MNIST. The `dpasp` stage fetches the four IDX
files (11.5 MB gzipped) into `/opt/mnist`, from torchvision's own mirror with
a fallback to the CVDF one, and verifies them against **torchvision's
published MD5s**; a truncated, substituted or redirected download fails the
build rather than training a network on rubbish. `curl --fail` matters here
for the same reason it always does — without it curl writes the HTTP error
page into the file and exits 0. The build then reads every file as `runner`
and decodes one, so a mode bit or a wrong path is a build failure and not a
`#python` traceback in a visitor's output panel.

The example reads them with `read_idx`, a `numpy.frombuffer` over the
decompressed bytes, and its comments say all of the above.

**The test set is cut to ten images.** The program pairs the two halves of the
test set, so ten images are five addition problems, and a neural program is
answered once per test row — `#query sum(X)` grounds to the 19 possible sums,
so the panel shows 5 blocks of 19. The full 10000-image test set would ask for
5000 blocks, which is 95000 probabilities: past the result cap, past the
deadline, and unreadable. `N_TEST_IMAGES` at the top of the `#python` block is
the knob, and the comments point at it.

**Training is not reduced** — all 60000 images, five iterations, `batch = 1000`,
exactly as published. It was worth measuring rather than assuming: that is
**43 seconds pinned to a single CPU**, so the README's old claim that training
exceeds the run limit was simply wrong. What made the example unrunnable was
the download, not the learning.

Measured end to end through the production bundle and a real runner: 36 s, 95
rows, five blocks peaking at `sum(8)`, `sum(6)`, `sum(10)`, `sum(5)` and
`sum(13)` — the digits are 7+1, 2+4, 1+9, 0+5, 4+9. Training is stochastic, so
four of five is a normal result too.

Four properties are pinned by `test_dockerfile.py`, which needs no daemon:
every file is fetched, every file is checksummed with `--fail` on the fetch,
the build checks readability as `runner`, and the example and the Dockerfile
agree on `/opt/mnist`. Each was mutation-checked — removing any one fails
exactly one test, by name.

**Every example source must end with a newline**, and a test enforces it.
That is not tidiness: dPASP's parser needs the newline to close a `%`
comment, so a file whose last line is

```prolog
#query joint. % P(joint) = 0.001
```

with nothing after it fails to parse outright —
`UnexpectedCharacters: No terminal matches '%' ... at line 28 col 15`. Found
when `poisson.pasp` arrived without one. The run path happens to hide it
(`submit` sends `content + '\n'`), but the stored source is also what a
download hands the user, so it has to be right on its own.

One other thing to know if you add an example with a `#python` block:
**indent its bodies by a multiple of the enclosing indent.** CodeMirror's
legacy Python mode tracks scopes by indentation, and a three-space body under
a `def` makes it read `return` as being outside the function and style it as
an error. The stock mode does this on its own — our `.pasp` mode delegates
faithfully and reproduces it exactly — so the fix is the example's whitespace,
not the highlighter. `poisson.pasp` had one such body and was renormalised to
four spaces; the program is unchanged.

Creating a file whose name already exists is refused, with the collision
named. It used to overwrite silently.

## Tests

```bash
cd web/editor && npm test              # 96 tests: tokenizer, examples, limits,
                                       #     runner URL, download, runnerFetch,
                                       #     file icons
cd web/editor && npm run check         # svelte-check: 0 errors, 0 warnings
cd web/editor && npm audit             # 0 vulnerabilities

# backend tests need the test-only extras:
#   cd web/backend && pip install -r requirements-dev.txt
cd web/backend && python3 -m pytest test_main.py      #  6: startup, readiness
cd web/backend/containerManager && python3 -m pytest  # 59: queue, lifecycle, limits,
                                                      #     liveness, network choice
cd web/backend/dockerProxy && python3 -m pytest       # 51: the socket policy, and the
                                                      #     real manager driving it
cd web/backend/dPaspRunner && python3 -m pytest       # 61: result format, limits,
                                                      #     blob endpoints, the
                                                      #     Dockerfile, MNIST cache
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
| "Some chunks are larger than 500 kB" | CodeMirror and flowbite bundled into the 527 kB page chunk | `manualChunks` in `vite.config.ts` splits them out; the page node is now 43 kB beside a 400 kB shared chunk |
| "apt does not have a stable CLI interface" | `apt` used in `dPaspRunner/Dockerfile` | switched to `apt-get` |
| debconf frontend warnings | interactive apt in a non-interactive build | `DEBIAN_FRONTEND=noninteractive` |
| pip's root-user warning and version check | normal in a container, not actionable from inside the image | `PIP_ROOT_USER_ACTION` / `PIP_DISABLE_PIP_VERSION_CHECK` |
| `FromAsCasing` and `LegacyKeyValueFormat` from BuildKit | `FROM ... as` and `ENV key value` in `editor/Dockerfile` | `AS` and `ENV key=value`; the unused `cm_host` variable was dropped |
| A theme object printed to the server log on every render | a leftover `console.log` in `svelte-themes`, whose `<SvelteTheme />` did nothing — `app.html` hardcodes `class="dark"` and there is no theme toggle | dependency and component removed |
| "Could not detect a supported production environment", on every build | `@sveltejs/adapter-auto` recognises a handful of hosting platforms and none of them is a university server | `@sveltejs/adapter-node`, which also produces something runnable: `build/`, started with `node build` |
| `Cannot find base config file "./.svelte-kit/tsconfig.json"`, on a fresh checkout only | `tsconfig.json` extends a file that `svelte-kit sync` generates, and nothing ran sync first | every script that reads `tsconfig.json` now begins with `svelte-kit sync`, plus a `prepare` script — see the troubleshooting entry |
| `inflight@1.0.6` "leaks memory", plus `rimraf@2` and `glob@7` | one chain under `svelte-check` 3: `svelte-check → svelte-preprocess → sorcery → sander → rimraf@2 → glob@7 → inflight` | `svelte-check` upgraded to 4.x, which dropped `svelte-preprocess` from its dependencies and takes the whole chain with it (24 packages) |
| `npm warn Unknown project config "resolution-mode"` | `resolution-mode=highest` in `editor/.npmrc`. It is a **pnpm** option; npm has never had one by that name, so it did nothing but warn | line removed. npm already resolves to the highest version satisfying each range, which is what it was asking for |

`npm ci` is now completely silent — no deprecation notices, no config
warnings. `--force` is gone too: the dependency set resolves on its own, so
the flag (and its "I sure hope you know what you are doing" warning) was
stale.

What `editor/.npmrc` *does* still carry is `engine-strict=true`, and that one
earns its place. The framework upgrade moved the Node floor — `undici` 8
declares `node >= 22.19.0`, vitest 5 `^22.12 || ^24 || >=26` — and without
this npm prints `EBADENGINE` as a warning and installs anyway, so the first
symptom of a too-old Node would be a runner request failing at run time.
With it, `npm ci` fails immediately and says which package and which version.
(Checked by temporarily declaring `engines.node: ">=99"`: `npm error code
EBADENGINE`.)

### One build warning that stays

```
node_modules/@auth/core/lib/utils/cookie.js (1:30): The 'this' keyword is
equivalent to 'undefined' at the top level of an ES module, and has been
rewritten
```

Harmless, and it cannot be configured away from here. Two things to know.

**It is benign.** The line it points at is TypeScript's emitted helper
preamble:

```js
var __classPrivateFieldSet = (this && this.__classPrivateFieldSet) || function (…) { … };
```

The `this &&` guard is there precisely to cover the case where `this` is not
an object: rewritten to `undefined`, the left side is falsy and the `||`
branch — the real helper — is used. That is the intended path, not a
degraded one.

**It is not ours to silence.** It appears *after* `> Using
@sveltejs/adapter-node` in the build log, because the adapter runs its own
bundling pass over the server code, and that pass takes no configuration from
`vite.config.ts`. Neither `rollupOptions.onwarn` nor `onLog` sees it — both
were tried; `onLog` does receive Vite's own warnings, and this one is not
among them — and Rolldown's `checks` has no `thisIsUndefined` switch. It goes
away when `@auth/core` ships that file without the helper, and not before.

Resist silencing a deprecated transitive dependency with an npm `override`
unless the replacement is API-compatible. The tempting fix here —
`overrides: { rimraf, glob }` — quietly breaks `sander`, which calls
`rimraf(target, callback)` while rimraf 4+ exports an object rather than a
callable. It appears to work only because `sorcery` never calls that path.

A note on the `editor_node_modules` volume: it persists, and Docker fills a
named volume from the image only when the volume is *empty*, so it used to go
stale the moment `package.json` changed — `docker compose down -v` was part
of the ritual, and forgetting it broke the dev server outright (see the
troubleshooting entry above). The dev image now keeps its installed tree at
`/opt/node_modules` and its entrypoint copies that into the volume whenever
the lockfile's hash differs from the one stamped there. `up --build` is
enough.

## The framework upgrade

The whole front end moved a generation: **Svelte 4 → 5, SvelteKit 1 → 2,
Vite 4 → 8, vitest 1 → 5, Tailwind 3 → 4, `@auth/sveltekit` 0.3 → 1.x,
`undici` 5 → 8, `adapter-node` 1 → 5.** `npm audit` went from 17 advisories
(3 critical, 4 high) to **0**.

It was one change because it could not be several. The advisories were not
stray packages: `@auth/core` needed `@auth/sveltekit` 1.x, which needed
SvelteKit 2; SvelteKit 2 needed Vite 5+; vitest 1 pinned Vite 4; and
`flowbite-svelte@0.44` pinned **Svelte 4**, so it blocked the one upgrade
everything else was waiting on.

### flowbite is gone

`flowbite-svelte` 1.x requires Tailwind 4 and changed its component API, so
the nav bar and the file browser's dialogs were being rewritten either way.
The library was supplying eight components — `Navbar`/`NavBrand`/`NavUl`/
`NavLi`/`NavHamburger`, `Toolbar`/`ToolbarButton`/`Spinner`, `Modal`,
`Dropzone`, `Button`, `ButtonGroup` — and five icons, all of them thin
wrappers over Tailwind classes. `src/lib/ui/` holds local equivalents now:

| was | is | note |
| --- | --- | --- |
| `Navbar` + hamburger | plain `<nav>` in `+layout.svelte` | one link; the responsive menu had nothing to collapse |
| `Toolbar` + `ToolbarButton` | `<div class="toolbar">` + `<button>` | a disabled button now *looks* disabled, which is what the old `opacity-40 cursor-not-allowed` at each call site was working around |
| `Modal` | `src/lib/ui/Modal.svelte` | native `<dialog>` + `showModal()`: the browser supplies the backdrop, top layer, focus trap and Escape-to-close |
| `Dropzone` | `src/lib/ui/Dropzone.svelte` | `<label>` around a visually hidden file input, so it stays focusable |
| `Button`, `ButtonGroup` | `src/lib/ui/Button.svelte`, one `.group` rule | two variants, which is all that was used |
| `flowbite-svelte-icons` | `src/lib/ui/icons/` | a handful of path strings on a 24×24 grid, one `Icon.svelte` |

That is ~250 lines of local code against two dependencies, two audit chains,
and the two bugs this project already hit through them (`Toolbar` being
`justify-between`, and `ToolbarButtonType` having no `'primary'`). The unused
`HoverMenu` went too — nothing imported it.

### Tailwind 4

`tailwind.config.cjs` and `postcss.config.cjs` are gone. The config is CSS
now: `src/app.css` has `@import "tailwindcss"`, a `@theme` block for the
`primary` scale, and `@custom-variant dark` in place of `darkMode: 'class'`.
Tailwind is a Vite plugin (`@tailwindcss/vite`) rather than a PostCSS one, so
`autoprefixer`, `postcss` and `postcss-load-config` left with it.

Four global overrides in the old `app.postcss` went as well — `.mt-4`,
`.rounded-lg`, `.container` and `menu`. Every one of them existed to fight a
flowbite component, and redefining a *utility class* globally is a trap:
`.mt-4 { margin-top: 0 }` silently breaks that utility everywhere.

**Preflight got broader, and it broke `<dialog>`.** Tailwind 4 applies

```css
*, ::before, ::after, ::backdrop, ::file-selector-button { margin: 0; … }
```

where Tailwind 3 reset margins on a *named list* of elements. A modal
`<dialog>` is centred by the browser's own stylesheet with `inset: 0` plus
`margin: auto` — so the new `*` selector quietly removed the `auto` and pinned
both dialogs to the top-left corner. `Modal.svelte` restates `margin: auto`,
and the comment there says why it must stay: it looks redundant against the UA
stylesheet precisely because something else is overriding that. Worth
remembering for anything else that leans on a UA default — `<dialog>`, the
`::backdrop`, list markers, `<fieldset>`.

### What to know about the Svelte 5 part

- `export let` → `$props()`, `$:` → `$derived`, slots → snippets,
  `on:click` → `onclick`. `svelte-check` reports **0 errors and 0 warnings**,
  which was the bar: Svelte 5 accepts the old syntax but deprecates it, so
  "it still compiles" would have left the warnings behind.
- **`$derived` for values, `$effect` for consequences.** The output panel
  auto-selects a tab when a result arrives, but a tab the user then clicks
  has to stick — so it is an `$effect` with a latch, not a derivation.
- `SplitPane` renamed `horizontal`/`vertical` to `columns`/`rows` and turned
  its slots into snippets.
- `@auth/sveltekit` 1.x: `SvelteKitAuth(...)` returns `{ handle, signIn,
  signOut }` where it used to *be* the handle, and `locals.getSession()`
  became `locals.auth()`.
- The dev and production images moved to **Node 24**: `undici` 8 declares
  `node >= 22.19` and vitest 5 `^22.12 || ^24 || >=26`, so Node 20 now fails
  at `npm ci`. Alpine still works — Rolldown (Vite 8) and Tailwind's oxide
  both publish `linux-{x64,arm64}-musl` binaries.

### The one override

```json
"overrides": { "cookie": "^0.7.2" }
```

`@sveltejs/kit@2.70.3` — the current release — depends on `cookie@^0.6.0`,
and `cookie < 0.7.0` carries GHSA-pxg6-pf52-xh8x. That is the entire
difference between "0 vulnerabilities" and four low-severity ones, and it is
upstream's to fix: `npm audit fix --force` proposes `@sveltejs/kit@0.0.30`,
which is not a fix.

This project's own advice is to resist overrides unless the replacement is
API-compatible (see *Build warnings*), so this one was checked rather than
assumed: the session cookie is set on a cold visit and **read back
unchanged** on the next request, which exercises both `serialize` and
`parse`. Remove it when SvelteKit moves its own pin.

### What was verified

`npm test` (71), `npm run check` (0/0), `npm audit` (0), `vite build`, and the
built server under `node build`.

End to end, against a stub runner on localhost — `DPASP_RUNNER_URL` points the
frontend at a single runner, which is the same hook the no-Docker setup uses:
`POST /api/instance/blob/list` and `POST /api/instance/run` both return the
runner's JSON through the real production bundle, and in Chromium the file
list populates, a file opens, the run button works and the probability table
renders with its semantics pills.

In a browser besides: the New file dialog opens, lists the seven examples,
suggests a filename and closes on Escape; the Upload drop zone renders with
its button correctly disabled; `BODY_SIZE_LIMIT` still answers 413 above the
limit; the anonymous `user_id` cookie is stable across requests; and with
OAuth credentials present `/auth/signin` returns 200 and offers GitHub.

**Not** verified: the Docker images, which cannot be built in the environment
these changes were written in.

**This list is longer than it was**, because the first pass did not include
the proxy path at all. The page was rendered with no container manager
running, so every API call 503'd before reaching `runnerFetch` — the panel
showed *"Could not reach the dPASP runner"*, which had a true explanation in
that environment and hid a real one in production. A visible error state in a
screenshot is not noise because you can explain it.

## Known gaps

- **One `overrides` entry is load-bearing.** `npm audit` is clean, but only
  because `cookie` is pinned forward past SvelteKit's own `^0.6.0` — see *The
  framework upgrade*. Drop the override once SvelteKit ships a release that
  depends on `cookie@^0.7`.
- **`pruneContainers` is never called.** Nothing schedules it, so containers
  live until the process exits rather than expiring after their configured
  lifetime. They are at least removed rather than left stopped now, and
  leftovers are swept at startup, but nothing enforces the lifetime while the
  manager runs.
- **Neural learning has no progress feedback.** `digitsum.pasp` trains for
  about 45 seconds and the panel shows only "running…" throughout. dPASP
  prints a learning bar, which the runner deliberately strips (it is
  per-line, not per-frame, so it would otherwise fill the output pane), but
  nothing takes its place. This is the clearest case for the submit-then-poll
  `/run` in *Next up*.
- **A neural program's test rows are shown as a flat table.** Every query is
  answered once per row and the rows are numbered in a `Row` column, which is
  honest but does not scale: at 50 rows (the cap) that is 50 blocks of
  identical query names to scroll through. Selecting a row, or charting one
  query across rows, would be the useful version. `digitsum.pasp` now runs and
  shows exactly this: 95 rows, of which the five that matter are the peak of
  each block.
- **CSV files are uploaded but not otherwise interpreted.** They land in the
  runner's blob folder, which is the working directory for a run, so a
  `#learn` directive or a `#python` block can open one by its bare name.
  There is no schema inspection or preview, and the file browser shows names
  only — no sizes or row counts.
- **A file over 1000 lines is read-only in the editor.** That is the safe
  behaviour, not the desirable one: a long *program* cannot be edited here at
  all. Making it editable means saving the edited head back over only the
  head, which needs a range-aware write on the runner rather than the
  whole-file `POST /blob/upload` that exists.
- **Uploads travel as one JSON string.** `submitUploadFile` reads the file
  with `File.text()` and posts it as `{filename, content}`, so a very large
  upload is held in memory three times over and is subject to whatever body
  limit the proxy and uvicorn impose. Multipart streaming would be the fix.
