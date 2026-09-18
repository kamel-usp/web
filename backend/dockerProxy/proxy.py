"""A Docker socket proxy that only lets through what the manager needs.

The container manager used to mount `/var/run/docker.sock`. This process
mounts it instead, listens on TCP inside the stack, and forwards the handful
of calls `policy.decide` allows. The manager reaches it through `DOCKER_HOST`,
so nothing in the manager changed.

Deliberately stdlib-only. The proxy is the most privileged thing in the stack
— it is the only container holding the socket — so its image installs no
packages and its dependencies are the ones Python ships with.

Responses are forwarded byte for byte rather than parsed and re-emitted, which
keeps `POST /build`'s progress stream live: the build log is what the README
tells an operator to watch, and buffering it until the build finished would
have made a ten-minute first build look like a hang.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler

import policy

#: The daemon's socket, inside this container.
DOCKER_SOCKET = os.getenv("DPASP_PROXY_SOCKET", "/var/run/docker.sock")

#: Where this proxy listens. Nothing publishes this port; it is reachable only
#: from the Compose network the container manager shares with it.
LISTEN_HOST = os.getenv("DPASP_PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("DPASP_PROXY_PORT", "2375"))

#: Compose services that may inspect their own container. The manager reads
#: its own labels to find its Compose project, which is how it resolves an
#: ambiguous runner network.
MANAGER_SERVICES = tuple(
    s.strip()
    for s in os.getenv(
        "DPASP_PROXY_MANAGER_SERVICES", "container-manager,container-manager-mock"
    ).split(",")
    if s.strip()
)

#: Request headers worth forwarding. Everything else — Host, Connection,
#: Content-Length, Transfer-Encoding — is set by this proxy.
FORWARDED_HEADERS = ("content-type", "accept", "user-agent", "accept-encoding")

HEADER_END = b"\r\n\r\n"
MAX_HEADER_BYTES = 256 * 1024


def with_connection_close(head: bytes) -> bytes:
    """Rewrite a response's header block to end the connection after it.

    The proxy opens a fresh connection upstream per request and closes it
    afterwards, so the client must be told not to reuse its own. Saying so is
    not optional and not cosmetic: without it the client's pool keeps a socket
    that is already closed, and the *next* request on it dies with

        RemoteDisconnected: Remote end closed connection without response

    which urllib3 will not retry for a POST — so a create, at random,
    disappears. Relying on the daemon to echo the `Connection: close` this
    proxy sends it is not enough; the guarantee has to be made here.
    """
    lines = head.split(b"\r\n")
    kept = [lines[0]] + [
        line
        for line in lines[1:]
        if not line.lower().startswith((b"connection:", b"keep-alive:"))
    ]
    kept.append(b"Connection: close")
    return b"\r\n".join(kept)


def log(*parts):
    print(*parts, flush=True)


class UnixHTTPConnection(http.client.HTTPConnection):
    """`http.client` over a unix socket, for the proxy's own small calls."""

    def __init__(self, path, timeout=30):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def inspect(ref: str) -> dict | None:
    """`GET /containers/<ref>/json`, or None if it is not there."""
    conn = UnixHTTPConnection(DOCKER_SOCKET)
    try:
        conn.request("GET", f"/containers/{ref}/json", headers={"Host": "docker"})
        response = conn.getresponse()
        payload = response.read()
        if response.status != 200:
            return None
        return json.loads(payload)
    except (OSError, ValueError):
        return None
    finally:
        conn.close()


class Ownership:
    """Answers "may the manager touch this container?", with a little memory.

    The Compose project is read once, from this proxy's own container: the
    proxy and the manager are services of the same project, so the proxy can
    recognise the manager without being told which container it is.
    """

    def __init__(self):
        self._project = None
        self._project_read = False
        self._lock = threading.Lock()

    def project(self):
        with self._lock:
            if not self._project_read:
                self._project_read = True
                me = inspect(socket.gethostname())
                labels = ((me or {}).get("Config") or {}).get("Labels") or {}
                self._project = labels.get("com.docker.compose.project")
                log(f"docker-proxy: Compose project {self._project!r}")
            return self._project

    def check(self, ref: str, self_allowed: bool) -> tuple[bool, str]:
        details = inspect(ref)
        if details is None:
            # Let the daemon answer a request for something that is not
            # there: a 404 from Docker is what the manager already handles,
            # and a 403 here would turn "already gone" into an error.
            return True, "absent"

        labels = ((details.get("Config") or {}).get("Labels")) or {}
        if policy.owns(labels):
            return True, "runner"

        if self_allowed:
            project = self.project()
            if (
                project
                and labels.get("com.docker.compose.project") == project
                and labels.get("com.docker.compose.service") in MANAGER_SERVICES
            ):
                return True, "self"

        return False, f"not a runner (labels={sorted(labels)})"


OWNERSHIP = Ownership()


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "dpasp-docker-proxy"
    sys_version = ""

    def log_message(self, fmt, *args):  # noqa: D102 - quieter default logging
        pass

    # One handler per method, all the same.
    def do_GET(self):
        self.proxy()

    def do_HEAD(self):
        self.proxy()

    def do_POST(self):
        self.proxy()

    def do_PUT(self):
        self.proxy()

    def do_DELETE(self):
        self.proxy()

    def read_body(self) -> bytes | None:
        """Buffer the request body. None means it was too large."""
        if (self.headers.get("Transfer-Encoding") or "").lower() == "chunked":
            chunks, total = [], 0
            while True:
                line = self.rfile.readline(65536).strip()
                size = int(line.split(b";")[0] or b"0", 16)
                if size == 0:
                    self.rfile.readline()  # trailing CRLF
                    break
                total += size
                if total > policy.MAX_BODY_BYTES:
                    return None
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks)

        length = int(self.headers.get("Content-Length") or 0)
        if length > policy.MAX_BODY_BYTES:
            return None
        return self.rfile.read(length) if length else b""

    def refuse(self, status: int, message: str):
        payload = json.dumps({"message": message}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.close_connection = True

    def proxy(self):
        self.close_connection = True

        body = self.read_body()
        if body is None:
            log(f"docker-proxy: DENY {self.command} {self.path} (body too large)")
            return self.refuse(413, "request body too large")

        decision = policy.decide(self.command, self.path, body)
        if not decision.allowed:
            log(
                f"docker-proxy: DENY {self.command} {self.path}: "
                f"{decision.reason}" + (f" [{decision.detail}]" if decision.detail else "")
            )
            return self.refuse(403, f"refused by the dPASP docker proxy: {decision.reason}")

        if decision.require_owned:
            allowed, why = OWNERSHIP.check(decision.require_owned, decision.self_allowed)
            if not allowed:
                log(
                    f"docker-proxy: DENY {self.command} {self.path}: "
                    f"{decision.require_owned} is {why}"
                )
                return self.refuse(
                    403,
                    "refused by the dPASP docker proxy: that container was not "
                    "created by this stack",
                )

        target = policy.rebuild_target(self.path, decision.path)
        forward_body = decision.body if decision.body is not None else body
        log(f"docker-proxy: {self.command} {target}")

        try:
            self.forward(target, forward_body)
        except OSError as e:
            log(f"docker-proxy: upstream failed: {e}")
            self.refuse(502, f"the Docker daemon could not be reached: {e}")

    def forward(self, target: str, body: bytes):
        """Send the request upstream and shovel the response back.

        The body is forwarded untouched, framing and all, so a chunked build
        log reaches the caller as it is produced. Only the response's header
        block is rewritten, and only to say `Connection: close`.
        """
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        upstream.settimeout(None)
        try:
            upstream.connect(DOCKER_SOCKET)

            lines = [f"{self.command} {target} HTTP/1.1", "Host: docker", "Connection: close"]
            for name in FORWARDED_HEADERS:
                value = self.headers.get(name)
                if value:
                    lines.append(f"{name}: {value}")
            lines.append(f"Content-Length: {len(body)}")
            request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body
            upstream.sendall(request)

            raw = self.connection
            head = b""
            while HEADER_END not in head:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                head += chunk
                if len(head) > MAX_HEADER_BYTES:
                    break

            block, separator, rest = head.partition(HEADER_END)
            raw.sendall(with_connection_close(block) + separator + rest)

            while True:
                data = upstream.recv(65536)
                if not data:
                    break
                raw.sendall(data)
        finally:
            upstream.close()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    if not os.path.exists(DOCKER_SOCKET):
        log(f"docker-proxy: {DOCKER_SOCKET} does not exist — is the socket mounted?")
        return 1

    log(
        f"docker-proxy: listening on {LISTEN_HOST}:{LISTEN_PORT}, "
        f"forwarding an allowlist to {DOCKER_SOCKET}"
    )
    with Server((LISTEN_HOST, LISTEN_PORT), ProxyHandler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
