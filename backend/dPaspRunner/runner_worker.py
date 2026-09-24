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

#: Heap one run may allocate, in MB, on top of what loading dPASP costs.
#: Bounds `RLIMIT_DATA`, not the address space — see `apply_memory_limit`.
DEFAULT_MEM_LIMIT_MB = 1024
DEFAULT_STACK_LIMIT_MB = 64

#: Everything the worker writes before this marker is runner noise (dPASP's
#: import-time notices) rather than output from the user's program.
OUTPUT_MARKER = "\x1e--dpasp-runner-ready--\x1e"

#: How many test instances' answers are sent to the browser at most. A neural
#: program answers every query once per row of test data, so a test set of any
#: realistic size would otherwise produce tens of thousands of table rows that
#: nobody can read. dPASP's own printer gives up sooner still — `cexact.c` has
#: `quiet = quiet || (data_stride > 10)`.
MAX_RESULT_INSTANCES = int(os.getenv("DPASP_MAX_RESULT_INSTANCES", "50"))


def apply_process_limits() -> None:
    """Disable core dumps and bound the stack.

    Neither of these interferes with loading libraries, so both are applied
    before anything is imported. The heap limit is not: see
    `apply_memory_limit`.
    """
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


def data_vm_bytes() -> int:
    """Bytes of data mappings this process already holds (`VmData`).

    This is the quantity `RLIMIT_DATA` bounds — brk plus private anonymous
    mappings — so it is the right baseline to measure a program's allowance
    from. Returns 0 where /proc is unavailable, which makes the limit
    absolute again rather than failing.
    """
    try:
        with open("/proc/self/status") as handle:
            for line in handle:
                if line.startswith("VmData:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


def apply_memory_limit(mem_limit_mb: int) -> None:
    """Cap the heap the *user's program* may add, and only then.

    A second line of defence *inside* the runner container, so that one
    pathological program cannot exhaust the memory the container as a whole is
    allowed. The container's own cgroup limits remain the primary control.

    Two decisions here, both of which cost a production bug before they were
    made.

    **`RLIMIT_DATA`, not `RLIMIT_AS`.** `RLIMIT_AS` bounds the whole virtual
    address space, including file-backed mappings of shared libraries, and
    importing PyTorch maps an enormous amount of address space without using
    anywhere near that much memory — measured here, `import pasp` with the
    CUDA build of torch peaks at 3.2 GB of address space while holding
    788 MB of data mappings. Under `RLIMIT_AS` the loader's `mmap` fails and
    the import dies with

        libtorch_python.so: failed to map segment from shared object

    `RLIMIT_DATA` exempts file-backed mappings, so libraries load while a
    runaway allocation still fails cleanly as a `MemoryError`.

    **Applied after the imports, and relative to what they cost.** The limit
    is for the user's program; our own runtime has to load whatever it loads.
    Setting it first made the loader itself the thing that hit the ceiling:
    on x86_64, `pip install torch` installs the CUDA build (there is no GPU in
    this container — `torch.cuda.is_available()` is False — but the libraries
    load anyway), and importing it takes ~790 MB of the old 1024 MB budget.
    That left ~230 MB for the actual program, and on a machine where the
    import needed a little more it crossed the line during loading:

        libc10_cuda.so: failed to map segment from shared object

    at a small overshoot, and a **segfault inside the dynamic loader** at a
    larger one (measured: 256 MB gives the message, 512 MB the segfault).
    On arm64 the same image gets a CPU-only torch with no CUDA libraries at
    all, which is why this failed on x86_64 hosts while working on Apple
    Silicon.

    So the budget is added to what is already in use: `mem_limit_mb` is how
    much the program may allocate, not how much the process may total.
    """
    if not mem_limit_mb or mem_limit_mb <= 0:
        return
    ceiling = data_vm_bytes() + mem_limit_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_DATA, (ceiling, ceiling))
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


def array_depth(value) -> int:
    """Nesting depth of `value`, counting a numpy array's own dimensions.

    Written so that the shaping below can be exercised with plain nested
    lists, while still reading `ndim` when handed the real `numpy.ndarray`
    dPASP returns.
    """
    depth = 0
    while True:
        ndim = getattr(value, "ndim", None)
        if isinstance(ndim, int):
            return depth + ndim
        if isinstance(value, (list, tuple)):
            depth += 1
            if not value:
                return depth
            value = value[0]
            continue
        return depth


def as_instances(answers) -> list:
    """Normalise dPASP's result array to one answer block per test instance.

    dPASP returns a *different shape* depending on whether the program has
    neural rules or annotated disjunctions (`exact.c`, around the
    `PyArray_SimpleNewFromData` call)::

        plain   (n_queries, n_values)
        neural  (n_test_instances, n_queries, n_values)

    with `n_values` being 2 under credal semantics (lower and upper) and 1
    under max-entropy. That extra leading dimension is what this function
    exists for. Read as if it were the plain shape, a neural program's
    per-query answers become the *values* of a single query: `poisson.pasp`
    asks two queries and gets back ``[[[0.147152], [0.001037]]]``, which the
    old code turned into one entry, ``ℙ(disaster) = [0.147152, 0.001037]`` —
    the second query's probability presented as the first query's upper bound.

    Returns a list of blocks, each a list of query rows, each a list of
    numbers; empty when there is nothing to report.
    """
    if answers is None:
        return []
    try:
        if len(answers) == 0:
            return []
    except TypeError:
        return []
    depth = array_depth(answers)
    if depth >= 3:
        return [[list(row) for row in block] for block in answers]
    if depth == 2:
        return [[list(row) for row in answers]]
    if depth == 1:
        # Not a shape dPASP currently produces; treated as one value per
        # query rather than silently dropped.
        return [[[value] for value in answers]]
    return []


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
    code = request.get("code") or ""
    # dPASP's own defaults, reported if the program does not parse. Once it
    # does, both are read back from the parsed program — see below.
    sem, psem = "stable", "credal"
    cwd = request.get("cwd")
    mem_limit_mb = int(request.get("mem_limit_mb") or DEFAULT_MEM_LIMIT_MB)

    apply_process_limits()

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

    # Only now: everything above is our own runtime loading itself, and
    # bounding that is how `libc10_cuda.so: failed to map segment from shared
    # object` happened. See `apply_memory_limit`.
    apply_memory_limit(mem_limit_mb)

    # Importing dPASP prints its own notices (for example a warning when
    # PyTorch is absent). Those belong to the runner, not to the user's
    # program, so the parent discards everything before this marker.
    sys.stdout.write(OUTPUT_MARKER + "\n")
    sys.stdout.flush()

    try:
        # No `semantics=` argument: the program decides. dPASP pre-scans the
        # source for a `#semantics` directive and lets it override that
        # argument anyway, so passing one only created a second place where
        # the answer could come from — and the editor used to have dropdowns
        # doing exactly that, silently disagreeing with the program in front
        # of the user.
        program = pasp.parse(code, from_str=True)
    except Exception as exc:
        result["error"] = error_payload("parse", exc)
        write_result(result_path, result, started)
        return 0

    try:
        # Report what dPASP actually used, read back from the parsed program
        # rather than echoed from the request. `program.semantics` is the
        # logic semantics after any `#semantics lstable.`; the probabilistic
        # half lands in `directives["psemantics"]` when declared, and is
        # credal when it is not.
        result["sem"] = program.semantics.name.lower()
        declared = program.directives.get("psemantics") if program.directives else None
        if declared:
            result["psem"] = declared.get("psemantics", psem)

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

    instances = as_instances(answers)
    shown = instances[:MAX_RESULT_INSTANCES]
    result["instances"] = len(instances)
    result["instances_shown"] = len(shown)

    for index, block in enumerate(shown):
        for i, row in enumerate(block):
            text = queries[i] if i < len(queries) else f"query {i + 1}"
            values = [jsonable(v) for v in row]
            entry = {"query": text, "values": values}
            if len(values) >= 2:
                entry["lower"], entry["upper"] = values[0], values[1]
            elif values:
                entry["lower"] = entry["upper"] = values[0]
            # Only when there is something to disambiguate: a plain program
            # has exactly one block and its entries carry no index.
            if len(instances) > 1:
                entry["instance"] = index
            result["queries"].append(entry)

    # Credal inference returns [lower, upper] per query, max-entropy a single
    # value. The frontend uses this to decide whether to show a bound column.
    # Read off one *query row*, not off the outermost dimension, which for a
    # neural program counts test instances instead.
    first_row = next((row for block in shown for row in block), None)
    result["interval"] = first_row is not None and len(first_row) >= 2
    result["ok"] = True
    write_result(result_path, result, started)
    return 0


def write_result(path: str, result: dict, started: float) -> None:
    result["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    with open(path, "w") as handle:
        json.dump(result, handle)


if __name__ == "__main__":
    sys.exit(main())
