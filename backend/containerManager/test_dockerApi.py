"""
Tests for the runner container lifecycle.

`dockerApi` is instantiated without running `__init__`, so these tests need no
Docker daemon: a stub stands in for `docker.from_env()`.

    cd backend/containerManager && python3 -m pytest
"""

import docker
import pytest

from containerManager import dockerApi


class FakeContainer:
    def __init__(self, short_id="abc123", stop_error=None, remove_error=None):
        self.short_id = short_id
        self.stopped = False
        self.removed = False
        self.remove_forced = None
        self.labels = None
        self._stop_error = stop_error
        self._remove_error = remove_error

    def stop(self):
        if self._stop_error:
            raise self._stop_error
        self.stopped = True

    def remove(self, force=False):
        if self._remove_error:
            raise self._remove_error
        self.removed = True
        self.remove_forced = force


class FakeContainers:
    def __init__(self, container=None, get_error=None, listed=None):
        self.container = container
        self.get_error = get_error
        self.listed = listed if listed is not None else []
        self.list_filters = None
        self.run_kwargs = None

    def get(self, container_id):
        if self.get_error:
            raise self.get_error
        return self.container

    def list(self, all=False, filters=None):
        self.list_filters = filters
        return self.listed

    def run(self, image, **kwargs):
        self.run_kwargs = kwargs
        return self.container


class FakeNetwork:
    def __init__(self):
        self.connected = []

    def connect(self, container, aliases=None):
        self.connected.append((container, aliases))


class FakeNetworks:
    def __init__(self, network):
        self.network = network

    def list(self, names=None):
        return [self.network]


class FakeClient:
    def __init__(self, containers, networks=None):
        self.containers = containers
        self.networks = networks or FakeNetworks(FakeNetwork())


def api_with(client):
    """A dockerApi bound to a stub client, skipping docker.from_env()."""
    api = object.__new__(dockerApi)
    api.client = client
    return api


# --------------------------------------------------------------------------
# deleteContainer
# --------------------------------------------------------------------------

def test_delete_stops_and_removes():
    # Removal is the point: a merely stopped container keeps its endpoint on
    # the dpasp-instances network, which breaks the next `docker compose up`.
    container = FakeContainer()
    api = api_with(FakeClient(FakeContainers(container)))

    api.deleteContainer("abc123")

    assert container.stopped is True
    assert container.removed is True
    assert container.remove_forced is True


def test_delete_tolerates_a_missing_container():
    api = api_with(FakeClient(FakeContainers(get_error=docker.errors.NotFound("gone"))))
    api.deleteContainer("abc123")  # must not raise


def test_delete_still_removes_when_stop_fails():
    # A container that is already dead cannot be stopped, but must still be
    # removed, or it lingers exactly as before.
    container = FakeContainer(stop_error=docker.errors.APIError("already stopped"))
    api = api_with(FakeClient(FakeContainers(container)))

    api.deleteContainer("abc123")

    assert container.stopped is False
    assert container.removed is True


def test_delete_survives_a_removal_race():
    container = FakeContainer(remove_error=docker.errors.NotFound("raced"))
    api = api_with(FakeClient(FakeContainers(container)))
    api.deleteContainer("abc123")  # must not raise


def test_delete_reports_but_swallows_a_removal_error(capsys):
    container = FakeContainer(remove_error=docker.errors.APIError("busy"))
    api = api_with(FakeClient(FakeContainers(container)))

    api.deleteContainer("abc123")

    assert "Could not remove" in capsys.readouterr().out


# --------------------------------------------------------------------------
# createContainer
# --------------------------------------------------------------------------

def test_created_containers_are_labelled():
    # The label is how leftovers are found, since Compose does not manage
    # these containers.
    container = FakeContainer()
    containers = FakeContainers(container)
    network = FakeNetwork()
    api = api_with(FakeClient(containers, FakeNetworks(network)))

    short_id = api.createContainer()

    assert short_id == "abc123"
    assert containers.run_kwargs["labels"] == {"dpasp.role": "runner"}
    assert containers.run_kwargs["detach"] is True
    assert network.connected == [(container, ["dpasp-instance-abc123"])]


# --------------------------------------------------------------------------
# removeStaleContainers
# --------------------------------------------------------------------------

def test_stale_containers_are_removed_by_label():
    stale = [FakeContainer("aaa"), FakeContainer("bbb")]
    containers = FakeContainers(listed=stale)
    api = api_with(FakeClient(containers))

    api.removeStaleContainers()

    assert containers.list_filters == {"label": "dpasp.role=runner"}
    assert all(c.removed for c in stale)


def test_stale_sweep_continues_past_a_failure():
    stale = [
        FakeContainer("aaa", remove_error=docker.errors.APIError("busy")),
        FakeContainer("bbb"),
    ]
    containers = FakeContainers(listed=stale)
    api = api_with(FakeClient(containers))

    api.removeStaleContainers()

    assert stale[1].removed is True


def test_stale_sweep_tolerates_an_unreachable_daemon(capsys):
    class Failing(FakeContainers):
        def list(self, all=False, filters=None):
            raise docker.errors.APIError("daemon down")

    api = api_with(FakeClient(Failing()))
    api.removeStaleContainers()

    assert "Could not list stale containers" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Runner environment
#
# Runner containers are not Compose services, so this forwarding is the only
# way to configure them without editing dPaspRunner/Dockerfile. Before it
# existed, DPASP_RUN_TIMEOUT could not be set at all — which the README
# nevertheless told people to do.
# --------------------------------------------------------------------------

def test_runner_settings_are_forwarded(monkeypatch):
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "300")
    monkeypatch.setenv("DPASP_RUN_MEM_MB", "2048")
    monkeypatch.setenv("DPASP_MAX_OUTPUT", "1234")

    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment() == {
        "DPASP_RUN_TIMEOUT": "300",
        "DPASP_RUN_MEM_MB": "2048",
        "DPASP_MAX_OUTPUT": "1234",
    }


def test_unset_settings_are_omitted(monkeypatch):
    # Omitted rather than passed as "", so the runner's own defaults apply.
    for key in dockerApi.RUNNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "")

    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment() == {}


def test_unrelated_variables_are_not_forwarded(monkeypatch):
    # The container manager's own environment holds the Docker socket, the
    # runner target and whatever else the host has; none of it belongs in a
    # container that runs user programs.
    for key in dockerApi.RUNNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RUNNER_TARGET", "dpasp")
    monkeypatch.setenv("AUTH_SECRET", "hunter2")

    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment() == {}


def test_created_containers_receive_the_settings(monkeypatch):
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "300")
    for key in ("DPASP_RUN_MEM_MB", "DPASP_MAX_OUTPUT"):
        monkeypatch.delenv(key, raising=False)

    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()

    assert containers.run_kwargs["environment"] == {"DPASP_RUN_TIMEOUT": "300"}
