"""
Tests for the container manager's HTTP surface.

The point of these is the startup behaviour: the API must answer while the
runner image is still being built. Uvicorn binds its listening socket only
after the lifespan's startup block returns, so any Docker work done inline
there makes the whole service refuse connections — which is what the frontend
used to see as `ECONNREFUSED`.

    cd backend && python3 -m pytest test_main.py
"""

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

import main


class FakeManager:
    """Stands in for `containerManager`, with a build we control."""

    def __init__(self, lifetime, pre_allocate=2, docker_api=None, build_seconds=0.0):
        self.lifetime = lifetime
        self.build_seconds = build_seconds
        self.ready = False
        self.startup_error = None
        self.pre_allocated_containers = []
        self.assigned = {}
        self.stopped = False

    async def start(self):
        await asyncio.sleep(self.build_seconds)
        self.ready = True

    async def getContainer(self, user_id):
        self.assigned.setdefault(user_id, f"cid-{len(self.assigned)}")
        return self.assigned[user_id]

    def activeContainerCount(self):
        return len(self.assigned)

    def stopAllContainers(self):
        self.stopped = True


def wait_until_ready(client, timeout=5.0):
    """Poll /health until the background warmup completes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get("/health").json()["status"] == "ready":
            return
        time.sleep(0.02)
    raise AssertionError("manager never became ready")


@pytest.fixture
def client(monkeypatch):
    """A client whose manager takes a noticeable time to warm up."""
    made = {}

    def factory(lifetime, **kwargs):
        made["manager"] = FakeManager(lifetime, build_seconds=0.3, **kwargs)
        return made["manager"]

    monkeypatch.setattr(main, "containerManager", factory)
    with TestClient(main.app) as c:
        c.manager = made["manager"]
        yield c


def test_the_api_answers_while_the_image_is_building(client):
    # The decisive check: a response at all, rather than a refused connection.
    assert client.manager.ready is False

    response = client.get("/container_for_user/alice")

    assert response.status_code == 503
    assert "still being built" in response.json()["error"]


def test_health_reports_building_then_ready(client):
    assert client.get("/health").json()["status"] == "building"

    wait_until_ready(client)
    assert client.manager.ready is True

    body = client.get("/health").json()
    assert body["status"] == "ready"
    assert body["active_containers"] == 0


def test_a_container_is_handed_out_once_ready(client):
    wait_until_ready(client)

    first = client.get("/container_for_user/alice")
    assert first.status_code == 200
    container_id = first.json()["id"]

    # Same user, same container.
    again = client.get("/container_for_user/alice")
    assert again.json()["id"] == container_id

    # A different user gets a different one.
    other = client.get("/container_for_user/bob")
    assert other.json()["id"] != container_id


def test_a_startup_failure_is_reported_with_its_reason(monkeypatch):
    class BrokenManager(FakeManager):
        async def start(self):
            self.startup_error = "BuildError: clingo has no installation candidate"

    monkeypatch.setattr(
        main, "containerManager", lambda lifetime, **kw: BrokenManager(lifetime, **kw)
    )

    with TestClient(main.app) as c:
        health = c.get("/health").json()
        assert health["status"] == "error"
        assert "clingo" in health["detail"]

        # The reason reaches the caller, not a generic message.
        response = c.get("/container_for_user/alice")
        assert response.status_code == 503
        assert "clingo" in response.json()["error"]


def test_an_allocation_failure_is_reported(monkeypatch):
    class FailingManager(FakeManager):
        async def start(self):
            self.ready = True

        async def getContainer(self, user_id):
            raise RuntimeError("daemon went away")

    monkeypatch.setattr(
        main, "containerManager", lambda lifetime, **kw: FailingManager(lifetime, **kw)
    )

    with TestClient(main.app) as c:
        response = c.get("/container_for_user/alice")
        assert response.status_code == 503
        assert "daemon went away" in response.json()["error"]


def test_shutdown_stops_the_containers(monkeypatch):
    made = {}

    def factory(lifetime, **kwargs):
        made["manager"] = FakeManager(lifetime, build_seconds=0.0, **kwargs)
        return made["manager"]

    monkeypatch.setattr(main, "containerManager", factory)

    with TestClient(main.app):
        pass

    assert made["manager"].stopped is True
