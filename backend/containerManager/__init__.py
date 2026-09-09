from .PriorityQueue import PriorityQueue
import time
import docker
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

    def createContainer(self):
        print("Spawning a container", flush=True)
        container = self.client.containers.run(
            "dpasp-runner",  # Specify the Docker image to use
            detach=True,  # Run the container in detached mode
            labels=dockerApi.RUNNER_LABELS,
        )
        print("A container was spawned", flush=True)
        net = self.client.networks.list(names="dpasp-instances")[0]
        net.connect(container, aliases=[f"dpasp-instance-{container.short_id}"])
        print(f"Created container with ID: {container.short_id}")
        return container.short_id

    def deleteContainer(self, container_id):
        """Stop a runner container and remove it.

        The removal matters. This used to only call `stop()`, so every runner
        ever spawned stayed on the host as an exited container, each still
        holding an endpoint on the `dpasp-instances` network. Compose does not
        manage those containers, so `docker compose down -v` deleted the
        network while they still referenced it, and the next `up` failed with

            failed to set up container networking: network <id> not found

        Removing the container releases its network endpoint.
        """
        try:
            container = self.client.containers.get(container_id)
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

    async def getContainer(self, user_id):
        if self.user_id_to_container_id.get(user_id) != None:
            return self.user_id_to_container_id[user_id]
        else:
            asyncio.create_task(self.allocContainers(1))

            if self.pre_allocated_containers:
                container_id = self.pre_allocated_containers.popleft()
            else:
                # The pool is empty: a burst of new users can outrun the
                # refill above. This used to `popleft()` unconditionally and
                # raise IndexError, failing the request outright; spawning one
                # on demand just makes this user wait for it instead.
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
