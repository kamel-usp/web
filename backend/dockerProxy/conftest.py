"""A fake Docker daemon, and the proxy standing in front of it.

Everything here exists so that the proxy's tests need no Docker: the fake is a
unix-socket HTTP server that records what it is asked and answers with the
shapes docker-py expects. What the daemon *received* is the assertion these
tests are built around — a policy that rewrites requests can only be checked
by looking at the bytes that came out the other side.
"""

import http.server
import json
import os
import socket
import socketserver
import tempfile
import threading

import docker
import pytest

import proxy

#: The id the fake daemon hands back from `POST /containers/create`.
RUNNER_ID = "runner00000000"

#: Labels the fake reports for containers that are not runners.
OTHER_CONTAINERS = {
    "frontend": {
        "com.docker.compose.project": "web",
        "com.docker.compose.service": "frontend",
    },
    "container-manager": {
        "com.docker.compose.project": "web",
        "com.docker.compose.service": "container-manager",
    },
    "other-stack-manager": {
        "com.docker.compose.project": "somebody-else",
        "com.docker.compose.service": "container-manager",
    },
}


#: Captured at import, not read per call: a test that patches
#: `socket.gethostname` to make the *manager* look like a particular container
#: would otherwise change what the fake daemon says about the *proxy* too, and
#: the two would move together in a way no real deployment does.
PROXY_HOSTNAME = socket.gethostname()


def labels_for(ref):
    if ref.startswith("dpasp-instance-") or ref.startswith("runner"):
        return {"dpasp.role": "runner"}
    if ref == PROXY_HOSTNAME:
        # The proxy inspecting itself, to learn its Compose project.
        return {
            "com.docker.compose.project": "web",
            "com.docker.compose.service": "docker-proxy",
        }
    return OTHER_CONTAINERS.get(ref, {"some": "label"})


class FakeDaemonHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def respond(self, status, payload=b"", content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def handle_one(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.seen.append((self.command, self.path, body))

        path = self.path.split("?", 1)[0]
        if path.startswith("/v1."):
            path = "/" + path.split("/", 2)[-1]

        if path == "/version":
            return self.respond(
                200, json.dumps({"ApiVersion": "1.41", "Version": "99"}).encode()
            )
        if path == "/_ping":
            return self.respond(200, b"OK", "text/plain")
        if path == "/containers/create":
            return self.respond(
                200, json.dumps({"Id": RUNNER_ID, "Warnings": []}).encode()
            )
        if path == "/containers/json":
            return self.respond(200, json.dumps(self.server.stale).encode())
        if path.startswith("/containers/") and path.endswith("/json"):
            ref = path[len("/containers/") : -len("/json")]
            return self.respond(200, json.dumps(self.server.inspect_reply(ref)).encode())
        if path.startswith("/containers/") and path.endswith("/logs"):
            # Docker multiplexes logs: one 8-byte header per frame (stream id,
            # three pad bytes, then a big-endian length), which docker-py
            # strips because the container's `Tty` is false. Sending the bare
            # text instead would arrive with its first eight characters eaten.
            text = b"the runner said something"
            frame = b"\x01\x00\x00\x00" + len(text).to_bytes(4, "big") + text
            return self.respond(200, frame, "application/octet-stream")
        if path.startswith("/containers/") and self.command in ("POST", "DELETE"):
            return self.respond(204)
        if path == "/networks":
            return self.respond(200, json.dumps(self.server.networks).encode())
        if path.startswith("/networks/") and path.endswith("/connect"):
            return self.respond(200, b"{}")
        if path.startswith("/networks/"):
            return self.respond(200, json.dumps({"Name": "bridge", "Id": "b1"}).encode())
        if path == "/build":
            return self.respond(200, b'{"stream":"Successfully built abc123\\n"}\n')
        if path.startswith("/images/") and path.endswith("/json"):
            return self.respond(200, json.dumps({"Id": "sha256:abc123"}).encode())
        return self.respond(404, json.dumps({"message": "no such endpoint"}).encode())

    do_GET = do_POST = do_DELETE = do_PUT = do_HEAD = handle_one


class FakeDaemon(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, path):
        self.seen = []
        #: What `GET /containers/json` returns — leftovers from a previous run.
        self.stale = []
        #: What `GET /networks` returns.
        self.networks = [
            {"Name": "web_dpasp-instances", "Id": "n1", "Labels": {}, "Driver": "bridge"}
        ]
        #: Container state reported by inspect, by reference.
        self.status = "running"
        super().__init__(path, FakeDaemonHandler)

    def inspect_reply(self, ref):
        return {
            "Id": ref,
            "Name": "/" + ref,
            "State": {"Status": self.status, "Running": self.status == "running",
                      "ExitCode": 0 if self.status == "running" else 1},
            # `Tty` is here because docker-py reads it before fetching logs,
            # to decide whether the stream is multiplexed.
            "Config": {"Labels": labels_for(ref), "Tty": False},
            "NetworkSettings": {"Networks": {}},
        }

    # UnixStreamServer hands the handler an empty client address, which
    # BaseHTTPRequestHandler indexes when building its log prefix.
    def get_request(self):
        request, _ = super().get_request()
        return request, ("unix", 0)

    def body_of(self, method, contains):
        for seen_method, path, body in self.seen:
            if seen_method == method and contains in path:
                return json.loads(body) if body else {}
        raise AssertionError(f"no {method} matching {contains!r} in {self.paths()}")

    def path_of(self, method, contains):
        for seen_method, path, _ in self.seen:
            if seen_method == method and contains in path:
                return path
        raise AssertionError(f"no {method} matching {contains!r} in {self.paths()}")

    def paths(self):
        return [(m, p) for m, p, _ in self.seen]


@pytest.fixture()
def daemon_and_proxy(monkeypatch):
    """A fake daemon with the real proxy in front of it. Yields (daemon, url)."""
    directory = tempfile.mkdtemp()
    socket_path = os.path.join(directory, "docker.sock")

    daemon = FakeDaemon(socket_path)
    threading.Thread(target=daemon.serve_forever, daemon=True).start()

    monkeypatch.setattr(proxy, "DOCKER_SOCKET", socket_path)
    monkeypatch.setattr(proxy, "OWNERSHIP", proxy.Ownership())

    server = proxy.Server(("127.0.0.1", 0), proxy.ProxyHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        yield daemon, f"tcp://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        daemon.shutdown()
        daemon.server_close()


@pytest.fixture()
def stack(daemon_and_proxy):
    """The same, with a docker-py client already pointed at the proxy."""
    daemon, url = daemon_and_proxy
    client = docker.DockerClient(base_url=url, version="1.41")
    try:
        yield client, daemon
    finally:
        client.close()
