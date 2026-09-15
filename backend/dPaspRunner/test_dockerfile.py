"""Checks on the runner Dockerfile that do not need a Docker daemon.

The runner image has never been built in the environment where these changes
were written — the container registry is blocked there — so the one property
that failed in the field is pinned here by reading the file instead.

That property: **the image must not depend on the mode bits of the machine
that built it.** `COPY` preserves them, a checkout made under umask 077 gives
0600 root-owned files, and since the server stopped running as root those are
unreadable to it. The symptom is the container exiting immediately with

    PermissionError: [Errno 13] Permission denied: '/app/main.py'

which reads as a bug in the runner and is really a bug in the build.
"""

import os
import re

DOCKERFILE = os.path.join(os.path.dirname(__file__), "Dockerfile")


def stages() -> dict:
    """Splits the Dockerfile into `{stage name: [instruction, ...]}`.

    Continuation lines are joined, so a multi-line `RUN` is one string.
    """
    with open(DOCKERFILE, encoding="utf-8") as f:
        text = f.read()

    text = re.sub(r"\\\n", " ", text)  # join continuations
    out, name = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        from_match = re.match(r"FROM\s+\S+(?:\s+AS\s+(\S+))?", line, re.I)
        if from_match:
            name = from_match.group(1) or line
            out[name] = []
            continue
        if name is not None:
            out[name].append(line)
    return out


def test_every_stage_that_drops_privilege_first_opens_up_the_app_tree():
    """`chmod -R a+rX` has to come after the last COPY and before USER."""
    dropped = {n: b for n, b in stages().items() if any(i.startswith("USER runner") for i in b)}
    assert dropped, "no stage runs as `runner` any more — has the image gone back to root?"

    for name, body in dropped.items():
        user_at = next(i for i, ins in enumerate(body) if ins.startswith("USER runner"))
        last_copy = max(i for i, ins in enumerate(body) if ins.startswith("COPY"))
        chmods = [
            i
            for i, ins in enumerate(body)
            if ins.startswith("RUN") and re.search(r"chmod\s+-R\s+a\+rX\s+/app", ins)
        ]
        assert chmods, f"stage {name!r} copies files in and drops to `runner` without a chmod"
        assert any(last_copy < i < user_at for i in chmods), (
            f"stage {name!r} has a chmod, but not between its last COPY "
            f"(instruction {last_copy}) and USER runner (instruction {user_at})"
        )


def test_the_dpasp_stage_proves_the_runner_can_read_its_entry_point():
    """A mode scan is not proof; reading the file as the user is."""
    body = stages()["dpasp"]
    assert any(
        ins.startswith("RUN") and "su -s /bin/sh runner" in ins and "/app/main.py" in ins
        for ins in body
    ), "the dpasp stage no longer checks, as `runner`, that /app/main.py is readable"


def test_the_runner_user_is_never_root():
    """uid 10001 in the image, because the manager passes the same number."""
    text = open(DOCKERFILE, encoding="utf-8").read()
    assert "--uid 10001" in text and "--gid 10001" in text
    for name, body in stages().items():
        users = [i for i in body if i.startswith("USER")]
        assert all(i == "USER runner" for i in users), f"stage {name!r}: {users}"
