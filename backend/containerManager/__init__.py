from .PriorityQueue import PriorityQueue
import time
import socket
import uuid
import docker
from docker.types import Ulimit
from collections import deque
import asyncio
import os


class dockerApi:
    def __init__(self):
        self.client = docker.from_env()

    def build_image(self):
        print(f"Building image (selected target:)", flush=True)
        print (os.getenv("RUNNER_TARGET"))
        try:
            self.image_id = self.client.images.build(path="./dPaspRunner", tag="dpasp-runner", quiet=False, target=os.getenv("RUNNER_TARGET"))
        except docker.errors.BuildError as e:
            for line in e.build_log:
                if 'stream' in line:
                    print(line['stream'].strip(), flush=True)
            raise e
        print("Done building image!", flush=True)

    #: Marks every container this manager creates. Runner containers are made
    #: through the Docker API rather than by Compose, so `docker compose down`
    #: does not know about them; the label is what makes the leftovers
    #: findable:
    #:     docker ps -aq --filter label=dpasp.role=runner | xargs -r docker rm -f
    RUNNER_LABELS = {"dpasp.role": "runner"}

    #: Settings forwarded from this process's environment into every runner
    #: container it creates.
    #:
    #: Runner containers are not Compose services, so nothing else gives them
    #: an environment: without this, the knobs `dPaspRunner` reads could only
    #: be changed by editing its Dockerfile. Compose passes these through to
    #: the container manager, and the manager passes them on.
    RUNNER_ENV_KEYS = (
        "DPASP_RUN_TIMEOUT",
        "DPASP_RUN_MEM_MB",
        "DPASP_MAX_OUTPUT",
    )

    #: The Compose network runners are attached to. Matched as a substring,
    #: because Compose prefixes network names with the project name
    #: (`web_dpasp-instances`).
    RUNNER_NETWORK = "dpasp-instances"

    #: Runner containers are *named* `dpasp-instance-<id>` rather than given
    #: that name as a network alias. On a user-defined network Docker's
    #: embedded DNS resolves container names, so the editor's
    #: `http://dpasp-instance-<id>` still works — and naming lets the
    #: container be created directly on the runner network, which an alias
    #: does not: `containers.run` takes `network=` but not `aliases=`, and
    #: attaching afterwards means the container spends its first moments on
    #: the default bridge, with a route to the internet.
    RUNNER_NAME_PREFIX = "dpasp-instance-"

    #: The account runners run as, as `uid:gid`.
    #:
    #: `dPaspRunner/Dockerfile` already ends with `USER runner`, so this is
    #: belt and braces — but it is the half that cannot be undone by editing
    #: the image, and it is stated numerically because that is all Docker
    #: compares. The two must agree: the `runner` account in the image is uid
    #: and gid 10001, high enough that no distribution hands it out first.
    RUNNER_USER = "10001:10001"

    def runnerEnvironment(self) -> dict:
        """The subset of `RUNNER_ENV_KEYS` actually set, for `containers.run`.

        Unset keys are omitted rather than passed as empty strings, so that
        the runner's own defaults apply.

        Thread counts are added on top, pinned to the container's CPU quota:
        PyTorch and OpenMP size their pools from the *host's* CPU count, which
        under a 1-CPU quota means a dozen threads fighting over one core and
        a slower run than a single thread would give.
        """
        environment = {
            key: os.environ[key]
            for key in dockerApi.RUNNER_ENV_KEYS
            if os.environ.get(key)
        }

        threads = str(max(1, int(self.runnerCpus())))
        for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
            # Set deliberately on the manager, it is forwarded as given;
            # otherwise it follows the CPU quota.
            environment[key] = os.environ.get(key) or threads

        return environment

    @staticmethod
    def runnerCpus() -> float:
        """CPU cores one runner may use. Fractions are allowed (0.5, 1.5)."""
        try:
            return max(0.1, float(os.getenv("DPASP_RUNNER_CPUS", "1.0")))
        except ValueError:
            return 1.0

    @staticmethod
    def runnerName(runner_id: str) -> str:
        return dockerApi.RUNNER_NAME_PREFIX + runner_id

    def runnerLimits(self) -> dict:
        """Everything that bounds one runner container, as `run` keywords.

        These are the *container's* limits, and they are the ones that matter:
        the rlimit inside `runner_worker` bounds one program's heap, but
        nothing there can stop a program from spawning processes, filling the
        disk, or talking to the network. A dPASP program may contain a
        `#python ... #end.` block, which is arbitrary Python executed in this
        container — so the container, not the code inside it, is the security
        boundary.

        Every value has an environment override, because the right numbers
        depend on the machine; `web/.env.example` lists them.

        - **CPU** (`DPASP_RUNNER_CPUS`, default 1.0) as `nano_cpus`, a hard
          quota rather than a share, so one user's grounding cannot slow
          everyone else's.
        - **Memory** (`DPASP_RUNNER_MEM`, default 2g) with `memswap_limit`
          equal to it, which is how Docker is told to allow no swap. Keep it
          above `DPASP_RUN_MEM_MB` plus what loading dPASP costs, or the
          kernel kills the worker before its own limit applies — `start`
          warns when the two are set too close.
        - **Processes** (`DPASP_RUNNER_PIDS`, default 256), so a fork bomb in
          a `#python` block exhausts its own container and nothing else.
        - **Capabilities**: all of them dropped, none added back. The runner
          listens on 8000 precisely so that it needs no `NET_BIND_SERVICE` to
          bind it, and it runs as uid 10001 (`RUNNER_USER`), not root.
          `no-new-privileges` stops a setuid binary from handing any of that
          back.
        - **A read-only root filesystem** (`DPASP_RUNNER_READONLY=0` to turn
          it off), with tmpfs for the two paths that must be writable: `/tmp`
          for the worker's result file, and `/blobs` for uploads. Both are
          `nosuid,nodev`, and `/blobs` is `noexec` as well — nothing there is
          ever meant to be executed. tmpfs is charged to the container's
          memory, so `DPASP_RUNNER_TMPFS_MB` has to fit inside
          `DPASP_RUNNER_MEM`.
        """
        # 3g, not 2g: the warning in `describeLimits` is the arithmetic —
        # 1 GB of program heap plus ~800 MB to load dPASP plus 256 MB of
        # tmpfs does not fit in 2 GB, and the symptom of getting it wrong is
        # the kernel killing the worker with no explanation.
        memory = os.getenv("DPASP_RUNNER_MEM", "3g")
        tmpfs_mb = int(os.getenv("DPASP_RUNNER_TMPFS_MB", "256"))

        limits = {
            "nano_cpus": int(self.runnerCpus() * 1_000_000_000),
            "mem_limit": memory,
            "memswap_limit": memory,
            "pids_limit": int(os.getenv("DPASP_RUNNER_PIDS", "256")),
            "user": dockerApi.RUNNER_USER,
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"],
            "ulimits": [Ulimit(name="nofile", soft=1024, hard=2048)],
        }

        if os.getenv("DPASP_RUNNER_READONLY", "1") != "0":
            limits["read_only"] = True
            limits["tmpfs"] = {
                "/tmp": "size=64m,mode=1777,nosuid,nodev",
                "/blobs": f"size={tmpfs_mb}m,mode=1777,noexec,nosuid,nodev",
            }

        return limits

    @staticmethod
    def parseMemory(value: str) -> int:
        """Docker's memory notation ("2g", "512m", "1073741824") in bytes.

        Returns 0 for anything unparseable, which callers treat as "unknown"
        rather than as "no memory".
        """
        text = str(value).strip().lower()
        units = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}
        scale = 1
        if text and text[-1] in units:
            scale = units[text[-1]]
            text = text[:-1]
        try:
            return int(float(text) * scale)
        except ValueError:
            return 0

    def describeLimits(self) -> list[str]:
        """Lines for the startup log: what runners are limited to, and why
        any of it looks wrong.

        Printed once at startup because these are the settings people most
        often need to see and least often think to check — and because a
        limit that is quietly too low shows up as a program being killed for
        no visible reason.
        """
        limits = self.runnerLimits()
        memory = limits["mem_limit"]
        lines = [
            "Runner limits: "
            f"{self.runnerCpus()} CPU, {memory} memory (no swap), "
            f"{limits['pids_limit']} processes, "
            f"{'read-only' if limits.get('read_only') else 'writable'} root, "
            f"uid {limits['user']}, all capabilities dropped"
        ]

        if os.getenv("DPASP_RUNNER_ALLOW_NETWORK") == "1":
            lines.append(
                "Runner network: OPEN. DPASP_RUNNER_ALLOW_NETWORK=1 attaches "
                "the default bridge, so programs can reach the internet."
            )
        else:
            lines.append(
                "Runner network: isolated. Runners are attached only to "
                f"{dockerApi.RUNNER_NETWORK}, which compose declares internal."
            )

        container_bytes = dockerApi.parseMemory(memory)
        program_bytes = int(os.getenv("DPASP_RUN_MEM_MB", "1024")) * 1024**2
        tmpfs_bytes = int(os.getenv("DPASP_RUNNER_TMPFS_MB", "256")) * 1024**2
        # Loading dPASP costs about this much before a program runs anything;
        # measured at 788 MB with the CUDA build of torch, ~300 MB CPU-only.
        runtime_bytes = 800 * 1024**2

        needed = program_bytes + runtime_bytes + (
            tmpfs_bytes if limits.get("read_only") else 0
        )
        if container_bytes and container_bytes < needed:
            lines.append(
                "WARNING: DPASP_RUNNER_MEM "
                f"({memory}) is below what one run can need "
                f"({needed // 1024**2} MB: {program_bytes // 1024**2} MB of "
                f"program heap, ~{runtime_bytes // 1024**2} MB to load dPASP"
                + (f", {tmpfs_bytes // 1024**2} MB of tmpfs" if limits.get("read_only") else "")
                + "). The kernel will kill the worker before its own limit "
                "applies, which the editor reports as 'killed by signal 9'."
            )

        return lines

    def composeProject(self):
        """The Compose project this manager belongs to, or None.

        Read from this container's own labels — `socket.gethostname()` is the
        container id inside a container — so that the runner network can be
        picked by project rather than by a name filter.
        """
        try:
            me = self.client.containers.get(socket.gethostname())
            return (me.labels or {}).get("com.docker.compose.project")
        except Exception:
            return None

    def runnerNetworkName(self) -> str:
        """The real name of the runner network.

        Compose prefixes it with the project name (`web_dpasp-instances`), and
        Docker's `names=` filter matches substrings, so the configured name is
        a filter rather than the thing itself — and a filter can match more
        than one network. Picking the wrong one is not a visible failure: the
        runner starts, the manager hands out its id, and the *frontend* fails
        to resolve the name, because the two are on different networks.

            getaddrinfo ENOTFOUND dpasp-instance-<id>

        So an ambiguous match is resolved by Compose's own labels, and
        `DPASP_RUNNER_NETWORK` names the network outright when that is not
        enough.
        """
        exact = (os.getenv("DPASP_RUNNER_NETWORK") or "").strip()
        if exact:
            return exact

        candidates = self.client.networks.list(names=dockerApi.RUNNER_NETWORK)
        if not candidates:
            raise RuntimeError(
                f"No network matching {dockerApi.RUNNER_NETWORK!r}. It is "
                "declared in compose.yaml and created with the stack; a "
                "runner cannot be reached without it."
            )
        if len(candidates) == 1:
            return candidates[0].name

        names = [n.name for n in candidates]
        project = self.composeProject()
        for network in candidates:
            labels = network.attrs.get("Labels") or {}
            if (
                labels.get("com.docker.compose.project") == project
                and labels.get("com.docker.compose.network") == dockerApi.RUNNER_NETWORK
            ):
                print(
                    f"Runner network: {network.name} (chosen from {names} by "
                    f"Compose project {project!r})",
                    flush=True,
                )
                return network.name

        raise RuntimeError(
            f"{len(candidates)} networks match {dockerApi.RUNNER_NETWORK!r} "
            f"({names}) and none of them belongs to this Compose project "
            f"({project!r}). Runners would land on whichever came first, and "
            "the frontend would fail to resolve them. Remove the stale ones "
            "(docker network rm), or set DPASP_RUNNER_NETWORK to the name to "
            "use."
        )

    def createContainer(self):
        print("Spawning a container", flush=True)
        environment = self.runnerEnvironment()
        if environment:
            print(f"Runner environment: {environment}", flush=True)

        runner_id = uuid.uuid4().hex[:12]

        container = self.client.containers.run(
            "dpasp-runner",  # Specify the Docker image to use
            detach=True,  # Run the container in detached mode
            name=dockerApi.runnerName(runner_id),
            # Naming the network here is what keeps the container off the
            # default bridge. Without it Docker attaches one anyway, and the
            # default bridge is masqueraded — so the runner would have a route
            # to the internet no matter what the runner network is declared
            # to be.
            network=self.runnerNetworkName(),
            labels=dockerApi.RUNNER_LABELS,
            environment=environment,
            **self.runnerLimits(),
        )
        print("A container was spawned", flush=True)

        if os.getenv("DPASP_RUNNER_ALLOW_NETWORK") == "1":
            # Deliberate opt-out: the runner network is internal, so programs
            # that fetch something — `digitsum.pasp` downloading MNIST, or a
            # `#learn` reading a CSV over https — cannot run without this.
            # Attaching the default bridge gives the container a gateway, and
            # with it the whole internet.
            print("DPASP_RUNNER_ALLOW_NETWORK=1: giving the runner a route out", flush=True)
            self.client.networks.get("bridge").connect(container)

        self.assertRunning(container, runner_id)

        print(f"Created container with ID: {runner_id}")
        return runner_id

    #: How long a just-created container is given to be `running`. `run` is
    #: supposed to return once it has started, so this is only slack.
    START_TIMEOUT_S = 5.0

    #: How long it then has to *stay* running before it is called good.
    #:
    #: Not optional, and the reason is a measurement: a container whose
    #: command exits immediately is still reported as `running` by the first
    #: `reload()` after `containers.run` returns. Checking once catches
    #: nothing — it loses the race with a process that dies in milliseconds,
    #: which is exactly the process worth catching. Verified against a real
    #: daemon with an image whose command is `exit 3`.
    STARTUP_GRACE_S = float(os.getenv("DPASP_RUNNER_START_GRACE", "0.75"))

    def assertRunning(self, container, runner_id):
        """Fail loudly if the container is not up, quoting its own output.

        A container that exits on startup is the worst kind of failure here,
        because nothing downstream says so: the manager hands out the id, the
        frontend builds `http://dpasp-instance-<id>:8000`, and the name no
        longer resolves — Docker drops a stopped container from its embedded
        DNS. What the user sees is

            getaddrinfo ENOTFOUND dpasp-instance-<id>

        which says nothing about the runner having died, let alone why. The
        container's own last lines usually say exactly why, so they are put
        into the error.
        """
        deadline = time.time() + dockerApi.START_TIMEOUT_S
        running = False
        while True:
            try:
                container.reload()
            except docker.errors.NotFound:
                raise RuntimeError(
                    f"The runner container {runner_id} vanished right after "
                    "being created."
                )
            if container.status == "running":
                running = True
                break
            if container.status in ("created", "restarting") and time.time() < deadline:
                time.sleep(0.2)
                continue
            break

        if running and dockerApi.STARTUP_GRACE_S > 0:
            # Look again: see STARTUP_GRACE_S.
            time.sleep(dockerApi.STARTUP_GRACE_S)
            try:
                container.reload()
                if container.status == "running":
                    return
            except docker.errors.NotFound:
                raise RuntimeError(
                    f"The runner container {runner_id} vanished moments after "
                    "starting."
                )
        elif running:
            return

        state = container.attrs.get("State", {})
        try:
            last = container.logs(tail=20).decode("utf8", "replace").strip()
        except docker.errors.APIError as e:
            last = f"(could not read its logs: {e})"

        try:
            container.remove(force=True)
        except docker.errors.APIError:
            pass  # leave it for the startup sweep

        raise RuntimeError(
            f"The runner container {runner_id} is {container.status} "
            f"(exit code {state.get('ExitCode')}) instead of running, so it "
            "was removed rather than handed out. Its last output was:\n"
            f"{last or '(nothing)'}"
        )

    def isRunning(self, runner_id) -> bool:
        """Whether a runner handed out earlier is still up.

        Pre-allocated containers wait in a queue, and an assigned one lives as
        long as its user's session: either can die in between — OOM-killed, or
        crashed — and a dead runner's name stops resolving.
        """
        try:
            container = self.client.containers.get(dockerApi.runnerName(runner_id))
        except (docker.errors.NotFound, docker.errors.APIError):
            return False
        return container.status == "running"

    def deleteContainer(self, container_id):
        """Stop a runner container and remove it.

        The removal matters. This used to only call `stop()`, so every runner
        ever spawned stayed on the host as an exited container, each still
        holding an endpoint on the `dpasp-instances` network. Compose does not
        manage those containers, so `docker compose down -v` deleted the
        network while they still referenced it, and the next `up` failed with

            failed to set up container networking: network <id> not found

        Removing the container releases its network endpoint.

        `container_id` is the short id this manager generated, not Docker's;
        the container is looked up by the name built from it.
        """
        try:
            container = self.client.containers.get(dockerApi.runnerName(container_id))
        except docker.errors.NotFound:
            return  # already gone; nothing to release

        try:
            container.stop()
        except docker.errors.APIError as e:
            print(f"Could not stop {container_id}: {e}", flush=True)

        try:
            container.remove(force=True)
        except docker.errors.NotFound:
            pass  # raced with Docker's own cleanup
        except docker.errors.APIError as e:
            print(f"Could not remove {container_id}: {e}", flush=True)

    def removeStaleContainers(self):
        """Remove leftover runner containers from a previous process.

        The manager holds its container registry in memory, so a restart
        orphans everything it had spawned — including the pre-allocated
        containers, which are created before any user asks for one. Clearing
        them at startup keeps them from accumulating across restarts.
        """
        try:
            stale = self.client.containers.list(
                all=True, filters={"label": "dpasp.role=runner"}
            )
        except docker.errors.APIError as e:
            print(f"Could not list stale containers: {e}", flush=True)
            return

        for container in stale:
            print(f"Removing stale runner {container.short_id}", flush=True)
            try:
                container.remove(force=True)
            except docker.errors.APIError as e:
                print(f"Could not remove {container.short_id}: {e}", flush=True)


class containerManager:
    def __init__(self, lifetime, pre_allocate=2, docker_api=None):
        # Built here rather than as a default argument value: a default is
        # evaluated at import time, so `import containerManager` used to open a
        # connection to the Docker daemon as a side effect. That made the
        # module — and therefore its own unit tests, including the ones that
        # only exercise PriorityQueue — unimportable without a running daemon.
        self.docker_api = docker_api if docker_api is not None else dockerApi()
        self.container_lifetime = lifetime
        self.pre_allocate = pre_allocate
        self.lifetime_pq = PriorityQueue()
        self.user_id_to_container_id = dict()
        self.pre_allocated_containers = deque()

        # Readiness, reported by the HTTP layer. `__init__` deliberately does
        # no Docker work at all: see `start`.
        self.ready = False
        self.startup_error = None

    async def start(self):
        """Build the runner image and fill the pool.

        Kept out of `__init__` on purpose. Uvicorn does not bind its listening
        socket until the lifespan's startup completes, so building the image
        during startup made the whole container-manager API refuse
        connections for as long as the build took — minutes on a cold cache,
        since the runner image compiles dPASP and downloads PyTorch. The
        frontend saw `ECONNREFUSED` instead of a message it could show.

        Awaited as a background task, so the API answers immediately and can
        report that it is still warming up. `build_image` is synchronous, so
        it goes to a worker thread rather than blocking the event loop.
        """
        try:
            if hasattr(self.docker_api, "describeLimits"):
                for line in self.docker_api.describeLimits():
                    print(line, flush=True)

            await asyncio.to_thread(self.docker_api.build_image)

            # Runner containers from a previous run of this process are
            # orphans: the registry above lives only in memory. Clear them
            # before pre-allocating, so restarts do not leave containers
            # behind holding endpoints on the `dpasp-instances` network.
            if hasattr(self.docker_api, "removeStaleContainers"):
                await asyncio.to_thread(self.docker_api.removeStaleContainers)

            await self.allocContainers(self.pre_allocate)
            self.ready = True
            print("Container manager ready", flush=True)
        except Exception as e:
            # Recorded rather than raised: this runs detached, and the HTTP
            # layer is what surfaces it to the user.
            self.startup_error = f"{type(e).__name__}: {e}"
            print(f"Container manager failed to start: {self.startup_error}", flush=True)

    def activeContainerCount(self):
        return len(self.user_id_to_container_id)

    async def allocContainers(self, count):
        list_of_awaitables = []
        for _ in range(count):
            list_of_awaitables.append(asyncio.to_thread(self.docker_api.createContainer))
        awaitable_list = asyncio.gather(*list_of_awaitables)
        self.pre_allocated_containers.extend(await awaitable_list)

    async def alive(self, container_id) -> bool:
        """Whether a runner is still running, when the API can say."""
        if not hasattr(self.docker_api, "isRunning"):
            return True
        return await asyncio.to_thread(self.docker_api.isRunning, container_id)

    async def getContainer(self, user_id):
        assigned = self.user_id_to_container_id.get(user_id)
        if assigned is not None:
            if await self.alive(assigned):
                return assigned
            # The user's container died under them — OOM-killed, or crashed.
            # Handing the id out again would send the frontend to a name
            # Docker no longer resolves, which reads as
            # `getaddrinfo ENOTFOUND dpasp-instance-<id>` and explains
            # nothing. Forget it and give them a fresh one.
            print(f"Container {assigned} for {user_id} is gone; replacing it", flush=True)
            self.user_id_to_container_id.pop(user_id, None)

        asyncio.create_task(self.allocContainers(1))

        container_id = None
        while self.pre_allocated_containers:
            candidate = self.pre_allocated_containers.popleft()
            if await self.alive(candidate):
                container_id = candidate
                break
            # A pooled container can die while it waits. Drop it quietly
            # rather than hand out a dead one.
            print(f"Pre-allocated container {candidate} is gone; skipping it", flush=True)

        if container_id is None:
            # The pool is empty, or held nothing alive: a burst of new users
            # can outrun the refill above. This used to `popleft()`
            # unconditionally and raise IndexError, failing the request
            # outright; spawning one on demand just makes this user wait.
            container_id = await asyncio.to_thread(self.docker_api.createContainer)

        self.user_id_to_container_id[user_id] = container_id

        self.lifetime_pq.insert(
            (container_id, user_id), time.time() + self.container_lifetime
        )
        return container_id

    def pruneContainers(self):
        while (
            not self.lifetime_pq.is_empty()
            and self.lifetime_pq.top_prio() < time.time()
        ):
            container_id, user_id = self.lifetime_pq.top()
            self.lifetime_pq.pop()
            self.user_id_to_container_id.pop(user_id)
            self.docker_api.deleteContainer(container_id)

    def stopAllContainers(self):
        for user_id, container_id in self.user_id_to_container_id.items():
            print(f"Stopping container {container_id} from {user_id}")
            self.docker_api.deleteContainer(container_id)

        for container_id in self.pre_allocated_containers:
            print(f"Stoppin pre allocated container {container_id}")
            self.docker_api.deleteContainer(container_id)
