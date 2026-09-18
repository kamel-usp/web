"""The proxy end to end: a real docker-py client, a fake daemon, no Docker.

`test_policy.py` checks the rules. This checks that they are actually applied
to the bytes on the wire — that the request the daemon receives is the
rewritten one, that a refusal reaches the caller as a `docker.errors.APIError`
it can handle, and that the client library's own behaviour (version
negotiation, the two-step create-then-start of `containers.run`) survives
going through a proxy at all.

The fake daemon is a unix-socket HTTP server that records what it is asked
and answers with the shapes docker-py expects. Standing it up is a few dozen
lines and removes the daemon from the test entirely: these run anywhere.
"""

import os
import tempfile

import docker
import pytest

import policy
from conftest import RUNNER_ID


def run_kwargs(**extra):
    base = dict(
        detach=True,
        name="dpasp-instance-0123456789ab",
        network="web_dpasp-instances",
        labels={"dpasp.role": "runner"},
        user="10001:10001",
    )
    base.update(extra)
    return base


# ---------------------------------------------------------------------------


def test_the_managers_own_create_goes_through(stack):
    client, daemon = stack
    container = client.containers.run("dpasp-runner", **run_kwargs(
        nano_cpus=1000000000, mem_limit="3g", pids_limit=256, read_only=True
    ))
    assert container.id == RUNNER_ID

    sent = daemon.body_of("POST", "/containers/create")
    assert sent["HostConfig"]["NanoCpus"] == 1000000000
    assert sent["HostConfig"]["PidsLimit"] == 256
    # containers.run is create-then-start, and the start had to pass the
    # ownership check against the fake daemon's labels.
    assert any("/start" in p for _, p in daemon.paths())


def test_an_escape_attempt_reaches_the_daemon_defanged(stack):
    """The request is not refused — it is rewritten. Both would do; this is
    the stronger statement, because it holds even if the caller is lying about
    what it wants."""
    client, daemon = stack
    client.containers.run(
        "dpasp-runner",
        **run_kwargs(
            privileged=True,
            volumes={"/": {"bind": "/host", "mode": "rw"}},
            cap_add=["SYS_ADMIN"],
            pid_mode="host",
            security_opt=["seccomp=unconfined"],
            ports={"8000/tcp": 22},
        ),
    )
    host = daemon.body_of("POST", "/containers/create")["HostConfig"]
    assert host["Privileged"] is False
    assert host["Binds"] == [] and host["Mounts"] == []
    assert host["CapAdd"] == [] and host["CapDrop"] == ["ALL"]
    assert host["PidMode"] == ""
    assert host["SecurityOpt"] == ["no-new-privileges:true"]
    assert host["PortBindings"] == {}


def test_running_any_other_image_is_refused_before_the_daemon_hears_of_it(stack):
    client, daemon = stack
    with pytest.raises(docker.errors.APIError) as raised:
        client.containers.run("ubuntu", **run_kwargs())
    assert "dpasp proxy" in str(raised.value).lower() or "403" in str(raised.value)
    assert not any("/containers/create" in p for _, p in daemon.paths())


def test_the_frontend_cannot_be_removed(stack):
    client, daemon = stack
    with pytest.raises(docker.errors.APIError):
        client.api.remove_container("frontend", force=True)
    assert not any(m == "DELETE" for m, _ in daemon.paths())


def test_a_runner_can_be_removed(stack):
    client, daemon = stack
    client.api.remove_container("dpasp-instance-0123456789ab", force=True)
    assert any(m == "DELETE" for m, _ in daemon.paths())


def test_the_frontends_environment_cannot_be_read(stack):
    """Inspect is the quiet one: it leaks other services' secrets."""
    client, _ = stack
    with pytest.raises(docker.errors.APIError):
        client.containers.get("frontend")


def test_the_manager_may_inspect_itself_to_find_its_compose_project(stack):
    client, _ = stack
    details = client.api.inspect_container("container-manager")
    assert details["Config"]["Labels"]["com.docker.compose.service"] == "container-manager"


def test_a_manager_from_another_compose_project_may_not(stack):
    client, _ = stack
    with pytest.raises(docker.errors.APIError):
        client.api.inspect_container("other-stack-manager")


def test_listing_containers_is_narrowed_to_runners_on_the_way_through(stack):
    client, daemon = stack
    client.containers.list(all=True, filters={"label": "com.docker.compose.service=frontend"})
    path = daemon.path_of("GET", "/containers/json")
    assert "dpasp.role%3Drunner" in path
    assert "frontend" not in path


def test_exec_is_not_reachable_at_all(stack):
    client, daemon = stack
    with pytest.raises(docker.errors.APIError):
        client.api.exec_create("dpasp-instance-0123456789ab", "sh")
    assert not any("exec" in p for _, p in daemon.paths())


def test_no_image_can_be_built_through_the_proxy(stack):
    """The manager no longer builds; Compose does. So this must not work even
    though docker-py will happily try."""
    client, daemon = stack
    context = tempfile.mkdtemp()
    with open(os.path.join(context, "Dockerfile"), "w") as f:
        f.write("FROM scratch\n")

    with pytest.raises(docker.errors.APIError):
        client.images.build(path=context, tag="dpasp-runner", quiet=False)

    assert not any("/build" in p for _, p in daemon.paths())


def test_the_runner_image_can_still_be_looked_up(stack):
    """`ensureImage` is what replaced the build."""
    client, _ = stack
    assert client.api.inspect_image("dpasp-runner")["Id"] == "sha256:abc123"


def test_a_refusal_carries_an_explanation(stack):
    client, _ = stack
    with pytest.raises(docker.errors.APIError) as raised:
        client.api.inspect_container("frontend")
    assert "dpasp docker proxy" in str(raised.value).lower()


def test_the_proxy_survives_a_body_it_cannot_parse(stack):
    client, daemon = stack
    response = client.api._post(
        client.api._url("/containers/create") + "?name=dpasp-instance-0123456789ab",
        data=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 403
    assert "not JSON" in response.json()["message"]
    assert not any("/containers/create" in p for _, p in daemon.paths())
    # and the proxy is still answering afterwards
    assert client.version()["ApiVersion"] == "1.41"


def test_an_oversized_body_is_refused_rather_than_buffered(stack, monkeypatch):
    client, _ = stack
    monkeypatch.setattr(policy, "MAX_BODY_BYTES", 128)
    with pytest.raises(docker.errors.APIError):
        client.containers.run("dpasp-runner", **run_kwargs(environment={"X": "y" * 500}))
