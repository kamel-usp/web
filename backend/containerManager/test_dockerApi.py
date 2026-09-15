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
    def __init__(
        self,
        short_id="abc123",
        stop_error=None,
        remove_error=None,
        status="running",
        exit_code=0,
        output=b"",
    ):
        self.short_id = short_id
        self.stopped = False
        self.removed = False
        self.remove_forced = None
        self.labels = None
        self.status = status
        self.attrs = {"State": {"ExitCode": exit_code}}
        self.reloads = 0
        self._output = output
        self._stop_error = stop_error
        self._remove_error = remove_error

    def reload(self):
        self.reloads += 1

    def logs(self, tail=None):
        return self._output

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
        self.got = []

    def get(self, container_id):
        self.got.append(container_id)
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
    def __init__(self, name="web_dpasp-instances"):
        # Compose prefixes network names with the project name, so the
        # configured name is a filter and this is the real one.
        self.name = name
        self.connected = []

    def connect(self, container, aliases=None):
        self.connected.append((container, aliases))


class FakeNetworks:
    def __init__(self, network=None, listed=None):
        self.network = network if network is not None else FakeNetwork()
        self.listed = listed
        self.list_names = None
        self.got = []
        self.bridge = FakeNetwork("bridge")

    def list(self, names=None):
        self.list_names = names
        if self.listed is not None:
            return self.listed
        return [self.network]

    def get(self, name):
        self.got.append(name)
        return self.bridge


class FakeClient:
    def __init__(self, containers, networks=None):
        self.containers = containers
        self.networks = networks or FakeNetworks()


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
    containers = FakeContainers(container)
    api = api_with(FakeClient(containers))

    api.deleteContainer("abc123")

    assert container.stopped is True
    assert container.removed is True
    assert container.remove_forced is True
    # Looked up by the name createContainer gave it, not by the bare id:
    # the id is this manager's, not Docker's.
    assert containers.got == ["dpasp-instance-abc123"]


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

@pytest.fixture(autouse=True)
def no_startup_grace(monkeypatch):
    """Skip the post-start grace wait unless a test is about it."""
    monkeypatch.setattr(dockerApi, "STARTUP_GRACE_S", 0)


@pytest.fixture(autouse=True)
def default_runner_env(monkeypatch):
    """Start every test from the shipped defaults.

    The manager reads its limits from its own environment, and a developer's
    shell may have any of these set.
    """
    for key in (
        "DPASP_RUNNER_CPUS",
        "DPASP_RUNNER_MEM",
        "DPASP_RUNNER_PIDS",
        "DPASP_RUNNER_TMPFS_MB",
        "DPASP_RUNNER_READONLY",
        "DPASP_RUNNER_ALLOW_NETWORK",
        "DPASP_RUNNER_NETWORK",
        "DPASP_RUN_MEM_MB",
    ):
        monkeypatch.delenv(key, raising=False)


# --------------------------------------------------------------------------
# A container that does not stay up
#
# The failure this guards against: the container exits, the manager hands out
# its id anyway, and the frontend reports `getaddrinfo ENOTFOUND
# dpasp-instance-<id>` — because Docker drops a stopped container from its
# embedded DNS. The message says nothing about the runner having died.
# --------------------------------------------------------------------------

def test_a_container_that_exits_is_reported_with_its_own_output():
    dead = FakeContainer(status="exited", exit_code=1, output=b"boom: something failed\n")
    api = api_with(FakeClient(FakeContainers(dead)))

    with pytest.raises(RuntimeError) as raised:
        api.createContainer()

    message = str(raised.value)
    assert "exited" in message
    assert "exit code 1" in message
    assert "boom: something failed" in message
    # And it is not left lying around.
    assert dead.removed is True


def test_a_container_that_dies_moments_later_is_caught(monkeypatch):
    # The race the grace period exists for: `containers.run` returns, the
    # first reload still says "running", and the process exits right after.
    # Measured against a real daemon — checking once catches nothing.
    monkeypatch.setattr(dockerApi, "STARTUP_GRACE_S", 0.01)

    class DiesLate(FakeContainer):
        def reload(self):
            self.reloads += 1
            if self.reloads > 1:
                self.status = "exited"

    dying = DiesLate(output=b"uvicorn: error: could not start\n")
    api = api_with(FakeClient(FakeContainers(dying)))

    with pytest.raises(RuntimeError, match="could not start"):
        api.createContainer()


def test_a_container_still_starting_is_waited_for(monkeypatch):
    class Slow(FakeContainer):
        def reload(self):
            self.reloads += 1
            if self.reloads >= 3:
                self.status = "running"

    monkeypatch.setattr(dockerApi, "STARTUP_GRACE_S", 0)
    slow = Slow(status="created")
    api = api_with(FakeClient(FakeContainers(slow)))

    api.createContainer()  # must not raise

    assert slow.status == "running"


def test_isRunning_reports_a_missing_container():
    api = api_with(FakeClient(FakeContainers(get_error=docker.errors.NotFound("gone"))))
    assert api.isRunning("abc123") is False


def test_isRunning_reports_a_stopped_container():
    api = api_with(FakeClient(FakeContainers(FakeContainer(status="exited"))))
    assert api.isRunning("abc123") is False


def test_isRunning_reports_a_live_container():
    containers = FakeContainers(FakeContainer(status="running"))
    api = api_with(FakeClient(containers))

    assert api.isRunning("abc123") is True
    assert containers.got == ["dpasp-instance-abc123"]


# --------------------------------------------------------------------------
# Choosing the runner network
# --------------------------------------------------------------------------

def labelled(name, project, network="dpasp-instances"):
    net = FakeNetwork(name)
    net.attrs = {
        "Labels": {
            "com.docker.compose.project": project,
            "com.docker.compose.network": network,
        }
    }
    return net


def test_one_matching_network_is_used_as_is():
    networks = FakeNetworks(FakeNetwork("web_dpasp-instances"))
    api = api_with(FakeClient(FakeContainers(FakeContainer()), networks))

    assert api.runnerNetworkName() == "web_dpasp-instances"


def test_an_ambiguous_match_is_resolved_by_compose_project(monkeypatch):
    # A leftover network called exactly `dpasp-instances` also matches the
    # substring filter. Picking it would put runners somewhere the frontend
    # is not, which surfaces as an unresolvable hostname and nothing else.
    stale = labelled("dpasp-instances", "old-project")
    mine = labelled("web_dpasp-instances", "web")
    networks = FakeNetworks(listed=[stale, mine])
    api = api_with(FakeClient(FakeContainers(FakeContainer()), networks))
    monkeypatch.setattr(type(api), "composeProject", lambda self: "web", raising=False)

    assert api.runnerNetworkName() == "web_dpasp-instances"


def test_an_unresolvable_ambiguity_names_the_candidates(monkeypatch):
    networks = FakeNetworks(
        listed=[labelled("a_dpasp-instances", "a"), labelled("b_dpasp-instances", "b")]
    )
    api = api_with(FakeClient(FakeContainers(FakeContainer()), networks))
    monkeypatch.setattr(type(api), "composeProject", lambda self: "c", raising=False)

    with pytest.raises(RuntimeError, match="a_dpasp-instances"):
        api.runnerNetworkName()


def test_the_network_can_be_named_outright(monkeypatch):
    monkeypatch.setenv("DPASP_RUNNER_NETWORK", "chosen-by-hand")
    networks = FakeNetworks(listed=[])
    api = api_with(FakeClient(FakeContainers(FakeContainer()), networks))

    assert api.runnerNetworkName() == "chosen-by-hand"


def test_created_containers_are_labelled():
    # The label is how leftovers are found, since Compose does not manage
    # these containers.
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()

    assert containers.run_kwargs["labels"] == {"dpasp.role": "runner"}
    assert containers.run_kwargs["detach"] is True


def test_the_container_is_named_so_dns_resolves_it():
    # The editor asks for http://dpasp-instance-<id>. That used to be a
    # network alias; it is the container's name now, which is what allows the
    # container to be created directly on the runner network.
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    runner_id = api.createContainer()

    assert containers.run_kwargs["name"] == f"dpasp-instance-{runner_id}"
    assert len(runner_id) == 12


def test_ids_are_unique_per_container():
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    assert api.createContainer() != api.createContainer()


def test_the_runner_joins_only_the_internal_network():
    # The crux of the network isolation. Without `network=` at creation,
    # Docker attaches the default bridge, which is masqueraded — the runner
    # would reach the internet however the runner network is declared.
    containers = FakeContainers(FakeContainer())
    networks = FakeNetworks(FakeNetwork("web_dpasp-instances"))
    api = api_with(FakeClient(containers, networks))

    api.createContainer()

    assert containers.run_kwargs["network"] == "web_dpasp-instances"
    # Looked up by substring, because Compose prefixes the project name.
    assert networks.list_names == "dpasp-instances"
    # Nothing else was attached.
    assert networks.got == []


def test_a_missing_runner_network_says_so():
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers, FakeNetworks(listed=[])))

    with pytest.raises(RuntimeError, match="dpasp-instances"):
        api.createContainer()


def test_network_access_can_be_opted_back_in(monkeypatch):
    # digitsum downloads MNIST and learning.pasp reads a CSV over https;
    # neither can run on an internal network.
    monkeypatch.setenv("DPASP_RUNNER_ALLOW_NETWORK", "1")
    container = FakeContainer()
    networks = FakeNetworks()
    api = api_with(FakeClient(FakeContainers(container), networks))

    api.createContainer()

    assert networks.got == ["bridge"]
    assert networks.bridge.connected == [(container, None)]


# --------------------------------------------------------------------------
# Runner limits
#
# A dPASP program may contain a `#python ... #end.` block, which is arbitrary
# Python executed inside the runner. The container is therefore the security
# boundary, and these are what bound it.
# --------------------------------------------------------------------------

def test_the_defaults_bound_cpu_memory_and_processes():
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()
    kwargs = containers.run_kwargs

    assert kwargs["nano_cpus"] == 1_000_000_000          # one core, a quota
    assert kwargs["mem_limit"] == "3g"
    assert kwargs["memswap_limit"] == "3g"               # equal → no swap
    assert kwargs["pids_limit"] == 256


def test_capabilities_are_dropped():
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()
    kwargs = containers.run_kwargs

    assert kwargs["cap_drop"] == ["ALL"]
    # Nothing is added back. The runner listens on 8000 rather than 80 so
    # that it needs no NET_BIND_SERVICE to bind it.
    assert "cap_add" not in kwargs
    assert kwargs["security_opt"] == ["no-new-privileges:true"]


def test_the_runner_does_not_run_as_root():
    # The image ends with `USER runner`; this is the half of it that survives
    # someone editing the image, and it is what Docker actually compares.
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()

    assert containers.run_kwargs["user"] == "10001:10001"


def test_the_root_filesystem_is_read_only_with_tmpfs_where_needed():
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()
    kwargs = containers.run_kwargs

    assert kwargs["read_only"] is True
    # /tmp holds the worker's result file, /blobs the user's uploads. Nothing
    # in either is ever executed on purpose.
    assert set(kwargs["tmpfs"]) == {"/tmp", "/blobs"}
    assert "noexec" in kwargs["tmpfs"]["/blobs"]
    assert "size=256m" in kwargs["tmpfs"]["/blobs"]
    assert all("nosuid,nodev" in opts for opts in kwargs["tmpfs"].values())


def test_file_descriptors_are_bounded():
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()
    [nofile] = containers.run_kwargs["ulimits"]

    assert nofile.name == "nofile"
    assert nofile.soft == 1024


def test_limits_can_be_tuned_per_machine(monkeypatch):
    monkeypatch.setenv("DPASP_RUNNER_CPUS", "0.5")
    monkeypatch.setenv("DPASP_RUNNER_MEM", "512m")
    monkeypatch.setenv("DPASP_RUNNER_PIDS", "64")
    monkeypatch.setenv("DPASP_RUNNER_TMPFS_MB", "32")
    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()
    kwargs = containers.run_kwargs

    assert kwargs["nano_cpus"] == 500_000_000
    assert kwargs["mem_limit"] == "512m"
    assert kwargs["pids_limit"] == 64
    assert "size=32m" in kwargs["tmpfs"]["/blobs"]


def test_a_nonsense_cpu_setting_falls_back_to_one_core(monkeypatch):
    monkeypatch.setenv("DPASP_RUNNER_CPUS", "plenty")
    api = api_with(FakeClient(FakeContainers(FakeContainer())))

    assert api.runnerLimits()["nano_cpus"] == 1_000_000_000


def test_the_read_only_root_can_be_turned_off(monkeypatch):
    # An escape hatch, because it is the limit most likely to break something
    # unforeseen inside the image.
    monkeypatch.setenv("DPASP_RUNNER_READONLY", "0")
    api = api_with(FakeClient(FakeContainers(FakeContainer())))

    limits = api.runnerLimits()

    assert "read_only" not in limits
    assert "tmpfs" not in limits


# --------------------------------------------------------------------------
# describeLimits
# --------------------------------------------------------------------------

def test_memory_notation_is_understood():
    assert dockerApi.parseMemory("2g") == 2 * 1024**3
    assert dockerApi.parseMemory("512m") == 512 * 1024**2
    assert dockerApi.parseMemory("1073741824") == 1024**3
    assert dockerApi.parseMemory("lots") == 0


def test_the_startup_lines_name_the_limits_and_the_isolation():
    api = api_with(FakeClient(FakeContainers(FakeContainer())))

    lines = " ".join(api.describeLimits())

    assert "1.0 CPU" in lines
    assert "uid 10001:10001" in lines
    assert "3g memory" in lines
    assert "isolated" in lines
    assert "WARNING" not in lines


def test_an_open_network_is_announced(monkeypatch):
    monkeypatch.setenv("DPASP_RUNNER_ALLOW_NETWORK", "1")
    api = api_with(FakeClient(FakeContainers(FakeContainer())))

    assert any("OPEN" in line for line in api.describeLimits())


def test_a_program_budget_larger_than_the_container_is_flagged(monkeypatch):
    # Set these two inconsistently and the kernel kills the worker before its
    # own limit applies, which reads as "killed by signal 9" and explains
    # nothing.
    monkeypatch.setenv("DPASP_RUN_MEM_MB", "4096")
    monkeypatch.setenv("DPASP_RUNNER_MEM", "1g")
    api = api_with(FakeClient(FakeContainers(FakeContainer())))

    warnings = [line for line in api.describeLimits() if line.startswith("WARNING")]

    assert len(warnings) == 1
    assert "signal 9" in warnings[0]


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

#: Set on every runner alongside whatever is forwarded; see below.
THREADS = {
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
}


def test_runner_settings_are_forwarded(monkeypatch):
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "300")
    monkeypatch.setenv("DPASP_RUN_MEM_MB", "2048")
    monkeypatch.setenv("DPASP_MAX_OUTPUT", "1234")

    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment() == {
        "DPASP_RUN_TIMEOUT": "300",
        "DPASP_RUN_MEM_MB": "2048",
        "DPASP_MAX_OUTPUT": "1234",
        **THREADS,
    }


def test_unset_settings_are_omitted(monkeypatch):
    # Omitted rather than passed as "", so the runner's own defaults apply.
    for key in dockerApi.RUNNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "")

    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment() == THREADS


def test_unrelated_variables_are_not_forwarded(monkeypatch):
    # The container manager's own environment holds the Docker socket, the
    # runner target and whatever else the host has; none of it belongs in a
    # container that runs user programs.
    for key in dockerApi.RUNNER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("RUNNER_TARGET", "dpasp")
    monkeypatch.setenv("AUTH_SECRET", "hunter2")

    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment() == THREADS


def test_thread_pools_are_pinned_to_the_cpu_quota(monkeypatch):
    # PyTorch and OpenMP size their pools from the *host's* CPU count, which
    # under a 1-CPU quota means a dozen threads contending for one core.
    monkeypatch.setenv("DPASP_RUNNER_CPUS", "2")
    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment()["OMP_NUM_THREADS"] == "2"


def test_a_fractional_cpu_quota_still_gets_one_thread(monkeypatch):
    monkeypatch.setenv("DPASP_RUNNER_CPUS", "0.5")
    api = api_with(FakeClient(FakeContainers()))

    assert api.runnerEnvironment()["OMP_NUM_THREADS"] == "1"


def test_an_explicit_thread_count_wins(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "4")
    api = api_with(FakeClient(FakeContainers()))

    # Only if someone set it deliberately on the manager: it is not in
    # RUNNER_ENV_KEYS, so it arrives only through this path.
    assert api.runnerEnvironment()["OMP_NUM_THREADS"] == "4"


def test_created_containers_receive_the_settings(monkeypatch):
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "300")
    for key in ("DPASP_RUN_MEM_MB", "DPASP_MAX_OUTPUT"):
        monkeypatch.delenv(key, raising=False)

    containers = FakeContainers(FakeContainer())
    api = api_with(FakeClient(containers))

    api.createContainer()

    assert containers.run_kwargs["environment"] == {
        "DPASP_RUN_TIMEOUT": "300",
        **THREADS,
    }
