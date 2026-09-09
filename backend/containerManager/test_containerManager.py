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

    def build_image(self):
        pass

    def removeStaleContainers(self):
        pass

    def createContainer(self):
        self.created += 1
        return f"container-{self.created - 1}"

    def deleteContainer(self, container_id):
        self.deleted.append(container_id)


async def settle():
    """Yield long enough for the pre-allocation tasks to finish."""
    for _ in range(5):
        await asyncio.sleep(0)
    await asyncio.sleep(0.05)


def test_a_user_keeps_the_same_container():
    async def scenario():
        docker = MockDocker()
        # Generous pre-allocation: `getContainer` pops from the deque without
        # checking, so a starved pool raises IndexError (see README, Known
        # gaps). This test is about identity, not that bug.
        manager = containerManager(60, pre_allocate=20, docker_api=docker)
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
        await settle()

        assigned = [await manager.getContainer(user) for user in range(2)]
        await settle()
        pre_allocated = list(manager.pre_allocated_containers)

        manager.stopAllContainers()

        for container_id in assigned + pre_allocated:
            assert container_id in docker.deleted

    asyncio.run(scenario())
