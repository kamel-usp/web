"""What the container manager is allowed to ask the Docker daemon to do.

This module is the security boundary, and it is deliberately the only
interesting file in the proxy: `decide()` is a pure function of one HTTP
request, so the whole policy can be read in one sitting and tested without a
daemon, a network, or a container.

The problem it exists to solve: the container manager creates runner
containers through the Docker API, which until now meant mounting
`/var/run/docker.sock` into it. That socket is root on the host — anyone who
can reach it can `create` a container with `Binds: ["/:/host"]` and
`Privileged: true` and walk out. The runners themselves are tightly bounded
(see the README's *What bounds a runner*), so the manager had become the
softest thing in the stack: the one component whose compromise gave away the
machine.

The proxy holds the socket; the manager talks to the proxy. Three kinds of
rule do the work:

1. **Allowlist.** Anything not named here is refused. `POST /containers/{id}/
   exec`, `GET /secrets`, `POST /swarm/init` and several hundred others are
   refused because they were never listed, not because someone thought to
   deny them.
2. **Forcing.** For `POST /containers/create` the dangerous fields are
   *overwritten*, not validated. A policy that checks the caller's request is
   only as good as the checker's imagination; a policy that sets the field
   itself does not care what was asked for. `Privileged` is false because the
   proxy makes it false.
3. **Ownership.** Anything naming an existing container — inspect, logs,
   stop, remove, start, network connect — is allowed only after the proxy has
   checked that the container carries `dpasp.role=runner`, or is the manager
   itself. That check needs the daemon, so it comes back as
   `require_owned`, and `proxy.py` performs it before forwarding.

What this does not defend against: a manager that has been compromised can
still create, inspect and destroy *runners* — bounded ones, on an internal
network, as uid 10001. It can no longer touch anything else on the host, and
it can no longer make the daemon **execute** anything of its choosing:
`POST /build` used to be allowed here, because the manager built the runner
image at startup. Compose builds it now, so the endpoint is gone from this
file and the last "run something as root" primitive went with it.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

#: The only image a container may be created from. Kept in step with
#: `containerManager.dockerApi.RUNNER_IMAGE`; Compose builds and tags it.
RUNNER_IMAGE = "dpasp-runner"

#: The label every runner carries, as `containerManager.RUNNER_LABELS` sets
#: it. This is what "owned by us" means, and the proxy verifies it against the
#: daemon rather than trusting the caller.
RUNNER_LABEL_KEY = "dpasp.role"
RUNNER_LABEL_VALUE = "runner"

#: Runner container names, as `dockerApi.runnerName` builds them.
RUNNER_NAME_RE = re.compile(r"^/?dpasp-instance-[0-9a-f]{6,32}$")

#: A network a runner may be created on or attached to. `dpasp-instances` is
#: matched as a substring because Compose prefixes the project name; `bridge`
#: is the deliberate opt-out behind DPASP_RUNNER_ALLOW_NETWORK.
RUNNER_NETWORK_SUBSTRING = "dpasp-instances"
CONNECTABLE_NETWORKS = ("bridge",)

#: docker-py prefixes every path with the negotiated API version.
VERSION_PREFIX = re.compile(r"^/v[0-9]+\.[0-9]+(?=/)")

#: Ceiling on a request body, in bytes. Every allowed request is small JSON —
#: the build context, which used to be the one large body, no longer comes
#: through here at all. The proxy buffers bodies in order to rewrite them, so
#: this bounds what one request can make it hold.
MAX_BODY_BYTES = int(os.getenv("DPASP_PROXY_MAX_BODY", str(1024 * 1024)))


@dataclass
class Decision:
    """The verdict on one request.

    `path` and `body` are the rewritten versions to forward; `None` means
    "unchanged". `require_owned` names a container that must be checked for
    the runner label before anything is forwarded — `proxy.py` does that, and
    turns a failure into a 403.
    """

    allowed: bool
    reason: str = ""
    path: str | None = None
    body: bytes | None = None
    require_owned: str | None = None
    #: True when `require_owned` may also be satisfied by the manager itself,
    #: which needs to inspect its own container to find its Compose project.
    self_allowed: bool = False
    #: Set on a denial, for the log line. Not sent to the caller.
    detail: str = ""


def deny(reason: str, detail: str = "") -> Decision:
    return Decision(allowed=False, reason=reason, detail=detail)


# ---------------------------------------------------------------------------
# `POST /containers/create`
# ---------------------------------------------------------------------------

#: Fields of `HostConfig` that are overwritten on every create, and the value
#: they are overwritten with. Between them these are every documented way to
#: leave the container: the host's filesystem (`Binds`, `Mounts`,
#: `VolumesFrom`), the host's devices (`Devices`, `DeviceRequests`,
#: `DeviceCgroupRules`), the host's namespaces (`PidMode`, `IpcMode`,
#: `UTSMode`, `UsernsMode`, `CgroupnsMode`, `Cgroup`), the host's kernel
#: (`Sysctls`, `Privileged`, `CapAdd`, `SecurityOpt`), the host's ports
#: (`PortBindings`, `PublishAllPorts`), the host's cgroup tree
#: (`CgroupParent`), an alternative runtime (`Runtime`), and /proc entries the
#: daemon masks by default (`MaskedPaths`, `ReadonlyPaths` — set to None so
#: the daemon applies its own list, which is what "leave it alone" has to mean
#: here: an empty list would *unmask* them).
FORCED_HOST_CONFIG = {
    "Privileged": False,
    "Binds": [],
    "Mounts": [],
    "VolumesFrom": [],
    "Devices": [],
    "DeviceRequests": [],
    "DeviceCgroupRules": [],
    "CapAdd": [],
    "CapDrop": ["ALL"],
    "SecurityOpt": ["no-new-privileges:true"],
    "PidMode": "",
    "IpcMode": "private",
    "UTSMode": "",
    "UsernsMode": "",
    "CgroupnsMode": "",
    "Cgroup": "",
    "CgroupParent": "",
    "Sysctls": {},
    "PortBindings": {},
    "PublishAllPorts": False,
    "ExtraHosts": [],
    "Runtime": "",
    "MaskedPaths": None,
    "ReadonlyPaths": None,
}

#: Forced on the container config itself. `User` is belt and braces with the
#: image's `USER runner` and with what the manager passes: three independent
#: places now have to be wrong at once for a runner to be root.
FORCED_CONFIG = {
    "User": "10001:10001",
    "Volumes": {},
}

#: Rejected outright rather than forced, because the manager never sets them
#: and a request that does is not the manager behaving normally.
REJECTED_CONFIG_KEYS = ("Entrypoint", "Cmd", "Shell")


def _is_runner_network(mode: str) -> bool:
    return bool(mode) and RUNNER_NETWORK_SUBSTRING in mode


def rewrite_create(query: dict, body: bytes) -> Decision:
    """Force a create request into the only shape a runner may have."""
    names = query.get("name") or []
    if len(names) != 1 or not RUNNER_NAME_RE.match(names[0]):
        return deny(
            "a container may only be created as dpasp-instance-<id>",
            f"name={names!r}",
        )

    try:
        config = json.loads(body or b"{}")
    except ValueError as e:
        return deny("the create request body is not JSON", str(e))
    if not isinstance(config, dict):
        return deny("the create request body is not an object")

    image = (config.get("Image") or "").split("@", 1)[0]
    if image not in (RUNNER_IMAGE, RUNNER_IMAGE + ":latest"):
        return deny(
            f"a container may only be created from {RUNNER_IMAGE}",
            f"Image={config.get('Image')!r}",
        )

    for key in REJECTED_CONFIG_KEYS:
        if config.get(key):
            return deny(f"{key} may not be overridden on a runner")

    host = config.get("HostConfig")
    if not isinstance(host, dict):
        host = {}

    mode = host.get("NetworkMode") or ""
    if not _is_runner_network(mode):
        return deny(
            "a runner may only be created on the "
            f"{RUNNER_NETWORK_SUBSTRING!r} network",
            f"NetworkMode={mode!r}",
        )

    endpoints = (config.get("NetworkingConfig") or {}).get("EndpointsConfig") or {}
    for name in endpoints:
        if not _is_runner_network(name):
            return deny(
                "a runner may not be created attached to "
                f"{name!r}",
            )

    host.update(FORCED_HOST_CONFIG)
    config.update(FORCED_CONFIG)
    config["HostConfig"] = host

    # The label is what every later ownership check reads, so the proxy sets
    # it rather than checking for it. A runner the manager forgot to label
    # would otherwise be one the manager could not clean up.
    labels = config.get("Labels")
    config["Labels"] = {
        **(labels if isinstance(labels, dict) else {}),
        RUNNER_LABEL_KEY: RUNNER_LABEL_VALUE,
    }

    return Decision(allowed=True, body=json.dumps(config).encode())


# ---------------------------------------------------------------------------
# `POST /networks/{id}/connect`
# ---------------------------------------------------------------------------


def rewrite_connect(network: str, body: bytes) -> Decision:
    if network not in CONNECTABLE_NETWORKS and not _is_runner_network(network):
        return deny(f"a runner may not be attached to {network!r}")
    try:
        payload = json.loads(body or b"{}")
    except ValueError as e:
        return deny("the connect request body is not JSON", str(e))
    target = payload.get("Container") if isinstance(payload, dict) else None
    if not target:
        return deny("a connect request must name a container")
    return Decision(allowed=True, require_owned=str(target))


# ---------------------------------------------------------------------------
# The allowlist itself
# ---------------------------------------------------------------------------

#: `GET /containers/json` — the manager lists its own leftovers at startup.
#: The label filter is forced rather than checked, so a list can never return
#: anything the manager does not own, whatever it asked for.
FORCED_LIST_FILTERS = {"label": [f"{RUNNER_LABEL_KEY}={RUNNER_LABEL_VALUE}"]}

CONTAINER_PATH = re.compile(r"^/containers/(?P<id>[^/]+)(?P<rest>/.*)?$")
NETWORK_PATH = re.compile(r"^/networks/(?P<id>[^/]+)(?P<rest>/.*)?$")


def decide(method: str, target: str, body: bytes = b"") -> Decision:
    """The whole policy, as one function of one request."""
    method = method.upper()
    split = urlsplit(target)
    path = VERSION_PREFIX.sub("", split.path) or "/"
    query = parse_qs(split.query, keep_blank_values=True)

    # Liveness and version negotiation: docker-py calls these before anything
    # else, and they say nothing about the host.
    if path in ("/_ping", "/version", "/info") and method in ("GET", "HEAD"):
        # /info reports the daemon's configuration, which is more than the
        # manager needs. Only the two it actually calls are allowed.
        if path == "/info":
            return deny("/info is not needed by the container manager")
        return Decision(allowed=True)

    # Read-only image metadata. `ensureImage` looks the runner image up at
    # startup; nothing here can create, tag, pull or delete one, and **there
    # is no `/build`**. Compose builds the runner image, so the web tier holds
    # no way to make the daemon execute a Dockerfile at all.
    if method == "GET" and re.match(r"^/images/[^/]+/json$", path):
        return Decision(allowed=True)

    if path == "/containers/json" and method == "GET":
        filters = dict(FORCED_LIST_FILTERS)
        kept = {k: v for k, v in query.items() if k in ("all", "limit", "size")}
        kept["filters"] = [json.dumps(filters)]
        return Decision(allowed=True, path="?" + urlencode(kept, doseq=True))

    if path == "/containers/create" and method == "POST":
        return rewrite_create(query, body)

    if path == "/networks" and method == "GET":
        return Decision(allowed=True)

    network_match = NETWORK_PATH.match(path)
    if network_match:
        network = network_match.group("id")
        rest = network_match.group("rest") or ""
        if method == "GET" and not rest:
            return Decision(allowed=True)
        if method == "POST" and rest == "/connect":
            return rewrite_connect(network, body)
        return deny(f"{method} {path} is not allowed on a network")

    container_match = CONTAINER_PATH.match(path)
    if container_match:
        ref = container_match.group("id")
        rest = container_match.group("rest") or ""

        # Inspecting a container is the one call the manager makes against
        # something that is not a runner: it reads its *own* labels to find
        # which Compose project it belongs to, which is how an ambiguous
        # runner network is resolved.
        if method == "GET" and rest == "/json":
            return Decision(allowed=True, require_owned=ref, self_allowed=True)
        if method == "GET" and rest == "/logs":
            return Decision(allowed=True, require_owned=ref)
        if method == "POST" and rest in ("/start", "/stop", "/kill", "/wait"):
            return Decision(allowed=True, require_owned=ref)
        if method == "DELETE" and not rest:
            return Decision(allowed=True, require_owned=ref)
        return deny(f"{method} {path} is not allowed on a container")

    return deny(f"{method} {path} is not on the allowlist")


def owns(labels: dict | None) -> bool:
    """Whether a container's labels mark it as one of ours."""
    return bool(labels) and labels.get(RUNNER_LABEL_KEY) == RUNNER_LABEL_VALUE


def rebuild_target(target: str, replacement: str | None) -> str:
    """Apply a `Decision.path` rewrite, keeping the API version prefix.

    A rewrite of the form `"?a=b"` replaces the query and keeps the path; a
    rewrite that starts with `/` replaces the path and keeps nothing.
    """
    if replacement is None:
        return target
    split = urlsplit(target)
    if replacement.startswith("?"):
        return urlunsplit(("", "", split.path, replacement[1:], ""))
    return replacement
