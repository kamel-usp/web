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
    └── dPaspRunner/        the runner image: FastAPI + dPASP (port 8000,
                            as a non-root user)
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

The runner image is **not** a Compose service — the container manager builds
it through the Docker API at its own startup, from the copy of
`backend/dPaspRunner` inside the manager image. So the fix travels host →
manager image → runner image, and picking it up means rebuilding both, which
is what `up --build` does:

```bash
docker compose --profile dpasp down
docker ps -aq --filter label=dpasp.role=runner | xargs -r docker rm -f
docker compose --profile dpasp up --build
```

`down` first because the manager caches its `/health` error for the life of
the process: rebuilding the image under a running manager changes nothing.

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
- **The runner containers still have no resource limits** (see *Known gaps*).
  On a shared machine that matters more than it does on a laptop: a runner
  can use as much CPU and memory as the host will give it for up to
  `DPASP_RUN_TIMEOUT` seconds, and it can reach the network.

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
`DPASP_RUN_MEM_MB` (default 1024), `DPASP_MAX_OUTPUT` (default 65536 chars).
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

The manager then also attaches the default bridge to each runner. Two of the
shipped examples need it: `digitsum.pasp` downloads MNIST, and
`learning.pasp` reads its CSV from a URL. Uploading the CSV and referring to
it by name works either way, which is why the example's comments recommend
it.

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

The container manager still mounts the Docker socket — the web tier can
control the daemon, which is the largest remaining hole and is in *Known
gaps*. Nothing here limits disk I/O bandwidth or the number of containers a
single visitor can cause to be created, either; `pruneContainers` exists for
the latter but nothing calls it.

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

The "New file" dialog offers a **Start from** dropdown seeded with six
programs, so a newcomer can run something real without typing it first:

| File | Shows |
| --- | --- |
| `earthquake.pasp` | probabilistic facts and rules, conditional queries |
| `insomnia.pasp` | the smallest program with non-degenerate credal bounds |
| `coloring.pasp` | L-stable semantics and `undef` queries |
| `prisoners.pasp` | interval-valued (credal) facts |
| `learning.pasp` | learnable facts (`?::`) fitted to a CSV with `#learn` |
| `digitsum.pasp` | `#python` blocks, neural rules and `#learn` |

The sources live in `editor/src/lib/examples/` as ordinary `.pasp` files and
are pulled in with Vite's `?raw`, rather than pasted into a TypeScript
literal. That keeps them readable and editable. All but `learning.pasp` are
currently byte-identical to their counterparts in the dPASP repository's own
`examples/` directory — `coloring.pasp` is `3coloring.plp` and
`digitsum.pasp` is `add_mnist.plp`, renamed only to match what the dialog
calls them. Diff them against upstream when dPASP changes. `learning.pasp`
comes from the [parameter-learning
tutorial](https://kamel-usp.github.io/pages/learn_dpasp.html#learning-the-parameters-of-programs)
and carries added comments.

The first four run in about a second and reproduce their published figures.
The other two are called out in the dialog when selected, rather than being
left to look broken:

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
* `digitsum.pasp` downloads MNIST and trains a network, so the first run may
  exceed even the 5-minute limit while it fetches MNIST.

Creating a file whose name already exists is refused, with the collision
named. It used to overwrite silently.

## Tests

```bash
cd web/editor && npm test              # 66 tests: tokenizer, examples, limits,
                                       #     runner URL, download
cd web/editor && npm run check         # svelte-check: 0 errors

# backend tests need the test-only extras:
#   cd web/backend && pip install -r requirements-dev.txt
cd web/backend && python3 -m pytest test_main.py      #  6: startup, readiness
cd web/backend/containerManager && python3 -m pytest  # 55: queue, lifecycle, limits,
                                                      #     liveness, network choice
cd web/backend/dPaspRunner && python3 -m pytest       # 42: result format, limits,
                                                      #     blob endpoints
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
| "Could not detect a supported production environment", on every build | `@sveltejs/adapter-auto` recognises a handful of hosting platforms and none of them is a university server | `@sveltejs/adapter-node` (pinned to 1.x, the SvelteKit 1 line), which also produces something runnable: `build/`, started with `node build` |
| `Cannot find base config file "./.svelte-kit/tsconfig.json"`, on a fresh checkout only | `tsconfig.json` extends a file that `svelte-kit sync` generates, and nothing ran sync first | every script that reads `tsconfig.json` now begins with `svelte-kit sync`, plus a `prepare` script — see the troubleshooting entry |
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

A note on the `editor_node_modules` volume: it persists, and Docker fills a
named volume from the image only when the volume is *empty*, so it used to go
stale the moment `package.json` changed — `docker compose down -v` was part
of the ritual, and forgetting it broke the dev server outright (see the
troubleshooting entry above). The dev image now keeps its installed tree at
`/opt/node_modules` and its entrypoint copies that into the volume whenever
the lockfile's hash differs from the one stamped there. `up --build` is
enough.

## Known gaps

- **`npm audit` reports 17 vulnerabilities, 3 of them critical.** They are
  not stray dependencies; they all trace to the pinned generation of the
  framework — Svelte 4 / SvelteKit 1 / Vite 4, plus `@auth/core` 0.15 and the
  `vitest` that pins to Vite 4. Every fix `npm audit` offers is a major
  version bump, so clearing them means a Svelte 5 + SvelteKit 2 + Vite 5
  migration rather than a dependency tweak. Deprecation warnings are already
  clear; this is the remaining dependency debt.
- **The container manager mounts the Docker socket**, which gives the web tier
  root-equivalent control of the host. With the runners themselves now
  bounded (see *What bounds a runner*), this is the largest remaining hole: a
  socket proxy restricted to the calls the manager actually makes, or a
  rootless daemon, is the usual answer.
- **`pruneContainers` is never called.** Nothing schedules it, so containers
  live until the process exits rather than expiring after their configured
  lifetime. They are at least removed rather than left stopped now, and
  leftovers are swept at startup, but nothing enforces the lifetime while the
  manager runs.
- **Learning is untested here.** A `#learn` program is dispatched correctly
  (`Program.__call__` handles it) but needs PyTorch and uploaded data; the
  result format reports it only through the `learned` flag.
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
