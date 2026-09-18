"""The real container manager, talking to the real proxy.

The claim this change rests on is that nothing in `containerManager` had to
change: it sets `DOCKER_HOST`, `docker.from_env()` reads it, and the same code
makes the same calls. A claim like that is worth exactly one test, and this is
it — `backend/containerManager/__init__.py` is imported unmodified and driven
against the proxy, with a fake daemon behind it recording what actually
arrived.

If a future change makes the manager call something the allowlist does not
cover, it fails here rather than in production, where it would show as the
editor never getting a runner.
"""

import os
import sys

import docker
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import containerManager  # noqa: E402  (after the path insert, deliberately)

from conftest import RUNNER_ID  # noqa: E402


@pytest.fixture()
def api(daemon_and_proxy, monkeypatch):
    """`containerManager.dockerApi`, pointed at the proxy. Yields (api, daemon)."""
    daemon, url = daemon_and_proxy
    monkeypatch.setenv("DOCKER_HOST", url)
    # The startup grace period is a real wait; the fake daemon's container is
    # not going to change its mind.
    monkeypatch.setattr(containerManager.dockerApi, "STARTUP_GRACE_S", 0.0)
    yield containerManager.dockerApi(), daemon


def test_the_manager_connects_through_the_proxy_at_all(api):
    """`docker.from_env()` reading DOCKER_HOST is the whole integration."""
    docker_api, daemon = api
    assert docker_api.client.version()["ApiVersion"] == "1.41"


def test_it_checks_the_runner_image_rather_than_building_it(api):
    """Compose builds the image; the manager only looks it up. That is what
    let `POST /build` come off the proxy's allowlist."""
    docker_api, daemon = api

    docker_api.ensureImage()

    assert any("/images/dpasp-runner/json" in p for _, p in daemon.paths())
    assert not any("/build" in p for _, p in daemon.paths())
    assert not hasattr(docker_api, "build_image")


def test_it_cannot_build_an_image_even_if_it_tries(api):
    """It still holds a client with a `build` method. What stops it is the
    proxy, not the absence of the call."""
    docker_api, daemon = api
    low_level = docker_api.client.api

    response = low_level._post(low_level._url("/build") + "?t=anything", data=b"")

    assert response.status_code == 403
    assert not any("/build" in p for _, p in daemon.paths())


def test_it_finds_the_runner_network(api):
    docker_api, _ = api
    assert docker_api.runnerNetworkName() == "web_dpasp-instances"


def test_it_creates_a_runner_and_the_daemon_sees_a_safe_request(api):
    docker_api, daemon = api
    runner_id = docker_api.createContainer()
    assert len(runner_id) == 12

    sent = daemon.body_of("POST", "/containers/create")
    host = sent["HostConfig"]
    # The manager's own limits arrived …
    assert host["NanoCpus"] == int(docker_api.runnerCpus() * 1e9)
    assert host["PidsLimit"] == int(os.getenv("DPASP_RUNNER_PIDS", "256"))
    # … and so did the proxy's, which the manager did not ask for.
    assert host["Privileged"] is False
    assert host["Binds"] == []
    assert host["MaskedPaths"] is None
    assert sent["User"] == "10001:10001"
    assert sent["Labels"]["dpasp.role"] == "runner"

    path = daemon.path_of("POST", "/containers/create")
    assert "name=dpasp-instance-" in path


def test_it_deletes_a_runner(api):
    docker_api, daemon = api
    docker_api.deleteContainer("0123456789ab")
    assert any("/stop" in p for _, p in daemon.paths())
    assert any(m == "DELETE" for m, _ in daemon.paths())


def test_it_sweeps_stale_runners_at_startup(api):
    docker_api, daemon = api
    daemon.stale = [
        {"Id": "runner1111", "Names": ["/dpasp-instance-aaaaaaaaaaaa"],
         "Image": "dpasp-runner", "Labels": {"dpasp.role": "runner"}, "State": "exited"}
    ]
    docker_api.removeStaleContainers()

    # The filter the manager sent was replaced by the proxy's own, so the
    # sweep can only ever see runners.
    path = daemon.path_of("GET", "/containers/json")
    assert "dpasp.role%3Drunner" in path
    assert any(m == "DELETE" for m, _ in daemon.paths())


def test_it_reports_a_runner_that_is_not_running(api):
    docker_api, daemon = api
    assert docker_api.isRunning("0123456789ab")
    daemon.status = "exited"
    assert not docker_api.isRunning("0123456789ab")


def test_a_dead_runner_is_refused_at_creation_through_the_proxy(api):
    """The liveness check reads logs and removes the container — both of
    which are calls the allowlist has to cover."""
    docker_api, daemon = api
    daemon.status = "exited"
    with pytest.raises(RuntimeError) as raised:
        docker_api.createContainer()
    assert "instead of running" in str(raised.value)
    assert "the runner said something" in str(raised.value)
    assert any(m == "DELETE" for m, _ in daemon.paths())


def test_it_can_read_its_own_compose_project(api, monkeypatch):
    """Used to disambiguate the runner network; the one inspect the manager
    makes against something that is not a runner."""
    import socket as socket_module

    docker_api, _ = api
    monkeypatch.setattr(
        containerManager.socket, "gethostname", lambda: "container-manager"
    )
    assert docker_api.composeProject() == "web"


def test_it_cannot_reach_past_the_allowlist_even_though_it_has_a_client(api):
    """The manager holds a full docker-py client. That is the point: what
    stops it is the proxy, not the absence of a method to call."""
    docker_api, daemon = api
    client = docker_api.client

    with pytest.raises(docker.errors.APIError):
        client.containers.run(
            "ubuntu",
            "sh",
            detach=True,
            privileged=True,
            volumes={"/": {"bind": "/host", "mode": "rw"}},
        )
    with pytest.raises(docker.errors.APIError):
        client.api.exec_create("frontend", "sh")
    with pytest.raises(docker.errors.APIError):
        client.containers.get("frontend")
    with pytest.raises(docker.errors.APIError):
        client.api.inspect_container("frontend")

    assert not any("/containers/create" in p for _, p in daemon.paths())
    assert not any("exec" in p for _, p in daemon.paths())
