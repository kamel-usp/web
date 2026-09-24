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


# --------------------------------------------------------------------------
# The MNIST cache
#
# `digitsum.pasp` used to call `torchvision.datasets.MNIST(download=True)`.
# A runner container has no route off the host and torchvision is not
# installed, so the example could not run at all. The dataset is baked into
# the image instead, and these pin the three properties that make that safe:
# it is verified, it is readable by the account that will read it, and the
# example and the Dockerfile agree on where it lives.
# --------------------------------------------------------------------------

MNIST_FILES = (
    "train-images-idx3-ubyte.gz",
    "train-labels-idx1-ubyte.gz",
    "t10k-images-idx3-ubyte.gz",
    "t10k-labels-idx1-ubyte.gz",
)

#: torchvision's own figures (`torchvision/datasets/mnist.py`). Repeated here
#: rather than imported, because the point is to detect the Dockerfile drifting
#: away from them.
MNIST_MD5 = {
    "train-images-idx3-ubyte.gz": "f68b3c2dcbeaaa9fbdd348bbdeb94873",
    "train-labels-idx1-ubyte.gz": "d53e105ee54ea40749a09fcbcd1e9432",
    "t10k-images-idx3-ubyte.gz": "9fb629c4189551a2d022fa330f9573f3",
    "t10k-labels-idx1-ubyte.gz": "ec29112dd5afa0611ce80d1b7f02629c",
}

DIGITSUM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "editor", "src", "lib", "examples", "digitsum.pasp",
)


def dpasp_text() -> str:
    return " ".join(stages()["dpasp"])


def test_the_dpasp_stage_fetches_all_four_mnist_files():
    text = dpasp_text()
    for name in MNIST_FILES:
        assert name in text, f"the dpasp stage does not fetch {name}"


def test_every_mnist_file_is_checksummed():
    """A download that silently returns an error page must fail the build."""
    text = dpasp_text()
    for name, digest in MNIST_MD5.items():
        assert digest in text, f"no checksum for {name} — is it torchvision's?"
    assert "md5sum" in text and "--check" in text, "the checksums are listed but never verified"
    # curl exits 0 on an HTTP error unless told otherwise, writing the error
    # body into the file. Then the checksum catches it — but only because
    # --fail did not.
    assert "--fail" in text, "curl without --fail writes HTTP error pages into the data files"


def test_the_runner_user_can_read_the_mnist_cache():
    """Same reasoning as /app/main.py: check it as the user, in the build."""
    body = stages()["dpasp"]
    assert any(
        ins.startswith("RUN") and "su -s /bin/sh runner" in ins and "/opt/mnist" in ins
        for ins in body
    ), "nothing checks, as `runner`, that /opt/mnist is readable"


def test_the_example_reads_the_path_the_dockerfile_writes():
    """Two files have to agree on one directory, so a test reads both."""
    with open(DIGITSUM, encoding="utf-8") as f:
        example = f.read()
    assert 'MNIST_DIR = "/opt/mnist"' in example, "digitsum.pasp no longer reads /opt/mnist"
    assert "/opt/mnist" in dpasp_text(), "the dpasp stage no longer populates /opt/mnist"
    # And on the file names inside it.
    for name in MNIST_FILES:
        if name.startswith("t10k") or name == "train-images-idx3-ubyte.gz" or "labels" in name:
            assert name in example, f"digitsum.pasp does not read {name}"


def test_the_example_does_not_reach_for_torchvision():
    """The reason the cache exists. Comments may name it; code may not."""
    with open(DIGITSUM, encoding="utf-8") as f:
        code = "\n".join(
            line for line in f.read().splitlines() if not line.lstrip().startswith("%")
        )
    assert "torchvision" not in code
