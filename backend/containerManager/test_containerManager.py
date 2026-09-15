"""
Tests for the container manager's bookkeeping.

`getContainer` is a coroutine and `containerManager.__init__` schedules the
pre-allocation with `asyncio.create_task`, so the manager has to be built
inside a running event loop. Each test therefore wraps its scenario in
`asyncio.run`, which keeps the file free of a pytest-asyncio dependency.
"""

import asyncio

from containerManager import containerManager


class MockDocker:
    """Stands in for `dockerApi`, with no Docker daemon involved."""

    def __init__(self):
        self.created = 0
        self.deleted = []
        self.builds = 0
        self.sweeps = 0
        #: Containers this fake considers dead, by id.
        self.dead = set()
        self.liveness_checks = []

    def build_image(self):
        self.builds += 1

    def removeStaleContainers(self):
        self.sweeps += 1

    def createContainer(self):
        self.created += 1
        return f"container-{self.created - 1}"

    def deleteContainer(self, container_id):
        self.deleted.append(container_id)

    def isRunning(self, container_id):
        self.liveness_checks.append(container_id)
        return container_id not in self.dead


async def settle():
    """Yield long enough for the pre-allocation tasks to finish."""
    for _ in range(5):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


def test_a_user_keeps_the_same_container():
    async def scenario():
        docker = MockDocker()
        # Pre-allocated generously so that this test exercises identity
        # rather than the on-demand spawn path.
        manager = containerManager(60, pre_allocate=20, docker_api=docker)
        await manager.start()
        await settle()

        first = [await manager.getContainer(user) for user in range(5)]
        await settle()

        # Asking again must hand back the same container, not a new one.
        for user, container_id in enumerate(first):
            assert await manager.getContainer(user) == container_id

        assert len(set(first)) == 5
        assert manager.activeContainerCount() == 5

    asyncio.run(scenario())


def test_expired_containers_are_pruned():
    async def scenario():
        lifetime = 0.2
        docker = MockDocker()
        manager = containerManager(lifetime, pre_allocate=20, docker_api=docker)
        await manager.start()
        await settle()

        expiring = [await manager.getContainer(user) for user in range(5)]
        await asyncio.sleep(lifetime * 1.5)

        # A second cohort, requested after the first has aged out.
        fresh = [await manager.getContainer(user) for user in range(5, 10)]
        await settle()

        assert manager.activeContainerCount() == 10

        manager.pruneContainers()

        assert manager.activeContainerCount() == 5
        assert sorted(docker.deleted) == sorted(expiring)

        # The survivors are still reachable and unchanged.
        for user, container_id in enumerate(fresh, start=5):
            assert await manager.getContainer(user) == container_id

    asyncio.run(scenario())


def test_stopping_everything_deletes_both_pools():
    async def scenario():
        docker = MockDocker()
        manager = containerManager(60, pre_allocate=4, docker_api=docker)
        await manager.start()
        await settle()

        assigned = [await manager.getContainer(user) for user in range(2)]
        await settle()
        pre_allocated = list(manager.pre_allocated_containers)

        manager.stopAllContainers()

        for container_id in assigned + pre_allocated:
            assert container_id in docker.deleted

    asyncio.run(scenario())


def test_construction_touches_no_docker():
    """The constructor must do no Docker work.

    Uvicorn binds its socket only after the lifespan's startup returns, so
    anything slow here makes the whole API refuse connections. The image
    build belongs in `start`, awaited in the background.
    """
    docker = MockDocker()
    manager = containerManager(60, pre_allocate=2, docker_api=docker)

    assert docker.builds == 0
    assert docker.sweeps == 0
    assert docker.created == 0
    assert manager.ready is False

    async def scenario():
        await manager.start()
        assert docker.builds == 1
        assert docker.sweeps == 1
        assert manager.ready is True

    asyncio.run(scenario())


def test_a_failed_startup_is_recorded_not_raised():
    """A detached task cannot usefully raise; the HTTP layer reports this."""

    class BrokenDocker(MockDocker):
        def build_image(self):
            raise RuntimeError("no such image")

    async def scenario():
        manager = containerManager(60, pre_allocate=1, docker_api=BrokenDocker())
        await manager.start()  # must not raise

        assert manager.ready is False
        assert "no such image" in manager.startup_error

    asyncio.run(scenario())


def test_an_empty_pool_spawns_on_demand():
    """A burst of new users used to hit IndexError on an empty deque."""

    async def scenario():
        docker = MockDocker()
        manager = containerManager(60, pre_allocate=0, docker_api=docker)
        await manager.start()

        assert len(manager.pre_allocated_containers) == 0

        container_id = await manager.getContainer("first-user")

        assert container_id is not None
        assert manager.activeContainerCount() == 1

    asyncio.run(scenario())


# --------------------------------------------------------------------------
# Handing out only live containers
#
# A stopped container disappears from Docker's embedded DNS, so its id is
# worse than useless: the frontend resolves nothing and reports
# `getaddrinfo ENOTFOUND dpasp-instance-<id>`, which names no cause.
# --------------------------------------------------------------------------

def test_a_dead_pre_allocated_container_is_skipped():
    async def scenario():
        docker = MockDocker()
        manager = containerManager(60, pre_allocate=3, docker_api=docker)
        await manager.start()
        await settle()

        # Everything in the pool died while it waited.
        docker.dead = set(manager.pre_allocated_containers)
        pooled = list(manager.pre_allocated_containers)

        container_id = await manager.getContainer("u")

        assert container_id not in pooled
        assert docker.liveness_checks  # it did look

    asyncio.run(scenario())


def test_a_users_container_is_replaced_when_it_dies():
    async def scenario():
        docker = MockDocker()
        manager = containerManager(60, pre_allocate=4, docker_api=docker)
        await manager.start()
        await settle()

        first = await manager.getContainer("u")
        await settle()

        # Same user, same container — while it is alive.
        assert await manager.getContainer("u") == first

        docker.dead.add(first)
        replacement = await manager.getContainer("u")

        assert replacement != first
        assert manager.user_id_to_container_id["u"] == replacement

    asyncio.run(scenario())


def test_liveness_is_optional_for_a_docker_api_without_it():
    # `alive` is guarded by hasattr so that older stubs — and any other
    # implementation of this interface — keep working.
    class Minimal(MockDocker):
        isRunning = None

        def __getattribute__(self, name):
            if name == "isRunning":
                raise AttributeError(name)
            return object.__getattribute__(self, name)

    async def scenario():
        docker = Minimal()
        manager = containerManager(60, pre_allocate=2, docker_api=docker)
        await manager.start()
        await settle()

        assert await manager.getContainer("u") is not None

    asyncio.run(scenario())
