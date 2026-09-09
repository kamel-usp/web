"""
Out-of-process worker that runs a single dPASP program.

The worker is deliberately a separate process rather than a function called
inside the FastAPI event loop, for three reasons:

1. dPASP's inference core writes its progress bar and results from C, on file
   descriptors 1 and 2. `contextlib.redirect_stdout` cannot see that output,
   and redirecting the descriptors in-process would steal uvicorn's own
   stdout and race between concurrent requests. As a child process its
   descriptors are captured cleanly by the parent.
2. Grounding an ill-behaved program can run for an unbounded time or allocate
   unbounded memory. A child can be given rlimits and killed on a deadline;
   an event-loop task cannot.
3. A segfault in the C extension takes down only the child.

Protocol: the request is JSON on stdin, the response is JSON written to the
file named by argv[1]. Anything the program itself prints stays on stdout and
stderr, where the parent collects it as the program's output.
"""

import json
import os
import resource
import sys
import time

DEFAULT_MEM_LIMIT_MB = 1024
DEFAULT_STACK_LIMIT_MB = 64

#: Everything the worker writes before this marker is runner noise (dPASP's
#: import-time notices) rather than output from the user's program.
OUTPUT_MARKER = "\x1e--dpasp-runner-ready--\x1e"


def apply_limits(mem_limit_mb: int) -> None:
    """Cap the child's address space and disable core dumps.

    These are a second line of defence *inside* the runner container, so that
    one pathological program cannot exhaust the memory the container as a
    whole is allowed. The container's own cgroup limits remain the primary
    control.
    """
    if mem_limit_mb and mem_limit_mb > 0:
        limit = mem_limit_mb * 1024 * 1024
        try:
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        except (ValueError, OSError):
            pass
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass
    try:
        stack = DEFAULT_STACK_LIMIT_MB * 1024 * 1024
        soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
        if hard == resource.RLIM_INFINITY or hard >= stack:
            resource.setrlimit(resource.RLIMIT_STACK, (stack, hard))
    except (ValueError, OSError):
        pass


def jsonable(x):
    """Make a float JSON-safe.

    Probability bounds are normally finite, but utility and MAP queries can
    yield +/-inf, and a query conditioned on an impossible event yields nan.
    `json.dumps` would emit bare `Infinity`/`NaN`, which is invalid JSON and
    fails `JSON.parse` in the browser, so non-finite values are passed on as
    strings and formatted by the frontend.
    """
    f = float(x)
    if f != f:
        return "nan"
    if f == float("inf"):
        return "inf"
    if f == float("-inf"):
        return "-inf"
    return f


def error_payload(kind: str, exc: BaseException) -> dict:
    """Build a structured error, with source coordinates when available.

    dPASP parses with Lark, whose exceptions carry `line`/`column`, which lets
    the editor point at the offending character instead of only printing a
    message.
    """
    err = {
        "kind": kind,
        "type": type(exc).__name__,
        "message": str(exc),
    }
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    if isinstance(line, int):
        err["line"] = line
    if isinstance(column, int):
        err["column"] = column
    return err


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: runner_worker.py <result-file>", file=sys.stderr)
        return 2
    result_path = sys.argv[1]

    request = json.loads(sys.stdin.read() or "{}")
    sem = request.get("sem") or "stable"
    psem = request.get("psem") or "credal"
    code = request.get("code") or ""
    cwd = request.get("cwd")
    mem_limit_mb = int(request.get("mem_limit_mb") or DEFAULT_MEM_LIMIT_MB)

    apply_limits(mem_limit_mb)

    # Uploaded data files live in the blob folder; run there so that a program
    # can refer to `data.csv` by its bare name.
    if cwd and os.path.isdir(cwd):
        os.chdir(cwd)

    result = {"ok": False, "sem": sem, "psem": psem, "queries": []}
    started = time.monotonic()

    try:
        import pasp
    except Exception as exc:  # pragma: no cover - import failure is fatal
        result["error"] = error_payload("internal", exc)
        write_result(result_path, result, started)
        return 1

    # Importing dPASP prints its own notices (for example a warning when
    # PyTorch is absent). Those belong to the runner, not to the user's
    # program, so the parent discards everything before this marker.
    sys.stdout.write(OUTPUT_MARKER + "\n")
    sys.stdout.flush()

    try:
        program = pasp.parse(code, from_str=True, semantics=sem)
    except Exception as exc:
        result["error"] = error_payload("parse", exc)
        write_result(result_path, result, started)
        return 0

    try:
        # A `#semantics` directive in the program wins over the UI selection,
        # matching the behaviour of the `pasp` command-line interpreter.
        declared = program.directives.get("psemantics") if program.directives else None
        if declared:
            result["psem"] = declared.get("psemantics", psem)
        else:
            program.directives["psemantics"] = {"psemantics": psem}

        result["learned"] = bool(program.directives and "learn" in program.directives)

        # `quiet` suppresses dPASP's own result printing (we serialise the
        # returned array instead) and `status` its progress bar, so that the
        # captured output holds only what the program itself printed.
        answers = program(quiet=True, status=False)
    except Exception as exc:
        result["error"] = error_payload("runtime", exc)
        write_result(result_path, result, started)
        return 0

    # Variable queries such as `#query(f(X))` are grounded during the call and
    # appended to `program.Q`, so the query list is only complete afterwards.
    queries = [str(q) for q in program.Q]

    rows = [] if answers is None else [list(row) for row in answers]
    for i, row in enumerate(rows):
        text = queries[i] if i < len(queries) else f"query {i + 1}"
        values = [jsonable(v) for v in row]
        entry = {"query": text, "values": values}
        if len(values) >= 2:
            entry["lower"], entry["upper"] = values[0], values[1]
        elif values:
            entry["lower"] = entry["upper"] = values[0]
        result["queries"].append(entry)

    # Credal inference returns [lower, upper] per query, max-entropy a single
    # value. The frontend uses this to decide whether to show a bound column.
    result["interval"] = bool(rows) and len(rows[0]) >= 2
    result["ok"] = True
    write_result(result_path, result, started)
    return 0


def write_result(path: str, result: dict, started: float) -> None:
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    with open(path, "w") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    sys.exit(main())
