"""
Parent-side API for running dPASP programs.

`run_program` spawns `runner_worker.py`, enforces a wall-clock deadline, and
returns a JSON-serialisable dict describing the run. It never raises for a
faulty user program: a bad program produces a result with `ok: False` and a
structured `error`.

Result shape
------------
    {
      "ok": bool,
      "sem": "stable" | "partial" | "lstable" | "smproblog",
      "psem": "credal" | "maxent",
      "interval": bool,          # true when bounds are lower/upper pairs
      "learned": bool,           # true when the program had a #learn directive
      "elapsed_ms": int,
      "queries": [
        {"query": "P(alarm | burglary)", "values": [0.9, 0.9],
         "lower": 0.9, "upper": 0.9}
      ],
      "output": str,             # what the program itself printed
      "error": null | {"kind": "parse"|"runtime"|"timeout"|"internal",
                       "type": str, "message": str,
                       "line": int?, "column": int?}
    }

Non-finite bounds are serialised as the strings "inf", "-inf" and "nan", since
JSON has no literals for them.
"""

import json
import os
import random
import re
import subprocess
import sys
import tempfile

import runner_worker

IS_MOCK = os.getenv("MOCK") == "y"

#: Wall-clock ceiling for one run. Grounding a program is not guaranteed to
#: terminate in any reasonable time, so the deadline is not optional.
RUN_TIMEOUT_S = float(os.getenv("DPASP_RUN_TIMEOUT", "30"))

#: Heap ceiling applied inside the worker, below the container's own memory
#: limit so that the worker dies before the container is OOM-killed. This
#: bounds `RLIMIT_DATA`; it is not an address-space limit, because bounding
#: the address space breaks `import torch` (see runner_worker.apply_limits).
RUN_MEM_LIMIT_MB = int(os.getenv("DPASP_RUN_MEM_MB", "1024"))

#: Cap on captured program output, so that a program printing in a loop cannot
#: return an unbounded response.
MAX_OUTPUT_CHARS = int(os.getenv("DPASP_MAX_OUTPUT", "65536"))

WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner_worker.py")

#: dPASP's progress bar redraws itself with carriage returns; strip it so the
#: output pane does not fill with spinner frames.
_PROGRESS_RE = re.compile(r"(?:Querying|Learning|Grounding|Counting)\s*:.*?(?:\r|$)")


def clean_output(text: str) -> str:
    """Remove runner noise and progress-bar frames, then truncate.

    Anything the worker printed before its ready marker comes from importing
    dPASP, not from the user's program, so it is dropped.
    """
    if not text:
        return ""
    marker = runner_worker.OUTPUT_MARKER
    if marker in text:
        text = text.split(marker, 1)[1]
    text = _PROGRESS_RE.sub("", text)
    # Keep only the last frame of any other carriage-return animation.
    text = "\n".join(line.split("\r")[-1] for line in text.split("\n"))
    text = "\n".join(line for line in text.split("\n") if line.strip() != "---")
    text = text.strip()
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n... output truncated ..."
    return text


def mock_result(sem: str, psem: str, code: str) -> dict:
    """Fabricate a plausible result, for running the stack without dPASP."""
    queries = re.findall(r"^[ \t]*#query\s*(\(.*)$", code, flags=re.MULTILINE)
    interval = psem == "credal"
    entries = []
    for i, q in enumerate(queries):
        low = round(random.random(), 6)
        high = round(low + (1 - low) * random.random(), 6) if interval else low
        entry = {
            "query": "P" + q.strip(),
            "values": [low, high] if interval else [low],
            "lower": low,
            "upper": high,
        }
        entries.append(entry)
    return {
        "ok": True,
        "sem": sem,
        "psem": psem,
        "interval": interval,
        "learned": False,
        "elapsed_ms": 0,
        "queries": entries,
        "output": "MOCK mode: probabilities are random numbers.",
        "error": None,
    }


def run_program(sem: str, psem: str, code: str, cwd: str = None) -> dict:
    """Run `code` under the given semantics and return a structured result."""
    if IS_MOCK:
        return mock_result(sem, psem, code)

    request = json.dumps(
        {
            "sem": sem,
            "psem": psem,
            "code": code,
            "cwd": cwd,
            "mem_limit_mb": RUN_MEM_LIMIT_MB,
        }
    )

    handle, result_path = tempfile.mkstemp(prefix="dpasp-result-", suffix=".json")
    os.close(handle)

    timed_out = False
    stdout = stderr = ""
    returncode = 0
    try:
        # `start_new_session` puts the worker in its own process group so that
        # a timeout kills any helper processes dPASP may have spawned, not just
        # the worker itself.
        completed = subprocess.run(
            [sys.executable, WORKER, result_path],
            input=request,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT_S,
            start_new_session=True,
        )
        stdout, stderr, returncode = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as expired:
        timed_out = True
        stdout = expired.stdout or ""
        stderr = expired.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf8", "replace")

    result = None
    try:
        with open(result_path) as f:
            content = f.read()
        if content:
            result = json.loads(content)
    except (OSError, ValueError):
        result = None
    finally:
        try:
            os.unlink(result_path)
        except OSError:
            pass

    # The marker only appears on stdout, so split there before merging the two
    # streams; stderr carries tracebacks, which are always worth showing.
    marker = runner_worker.OUTPUT_MARKER
    if marker in (stdout or ""):
        stdout = stdout.split(marker, 1)[1]
    output = clean_output((stdout or "") + (("\n" + stderr) if stderr else ""))

    if timed_out:
        return {
            "ok": False,
            "sem": sem,
            "psem": psem,
            "interval": psem == "credal",
            "learned": False,
            "elapsed_ms": int(RUN_TIMEOUT_S * 1000),
            "queries": [],
            "output": output,
            "error": {
                "kind": "timeout",
                "type": "Timeout",
                "message": (
                    f"The program did not finish within {RUN_TIMEOUT_S:g} seconds "
                    "and was stopped. Exact inference enumerates every total "
                    "choice, so its cost grows exponentially in the number of "
                    "probabilistic facts."
                ),
            },
        }

    if result is None:
        # The worker died without writing a result: a segfault in the C
        # extension, or the heap limit being hit.
        message = "The solver stopped unexpectedly."
        if returncode and returncode < 0:
            message += f" It was killed by signal {-returncode}."
            if -returncode == 9:
                message += (
                    " This is usually the memory limit; try a program with"
                    " fewer probabilistic facts."
                )
        elif "MemoryError" in (stderr or ""):
            message += " It ran out of memory."
        return {
            "ok": False,
            "sem": sem,
            "psem": psem,
            "interval": psem == "credal",
            "learned": False,
            "elapsed_ms": 0,
            "queries": [],
            "output": output,
            "error": {"kind": "runtime", "type": "SolverError", "message": message},
        }

    result.setdefault("ok", False)
    result.setdefault("queries", [])
    result.setdefault("interval", psem == "credal")
    result.setdefault("learned", False)
    result.setdefault("error", None)
    result["output"] = output
    return result
