"""
Tests for the runner's result format.

Run from `backend/dPaspRunner`:

    python3 -m pytest test_dpasp_api.py

Tests that need dPASP itself are skipped when it is not importable, so the
file is useful in a checkout that only runs the mock target.
"""

import importlib
import json
import os
import resource
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dpasp_api  # noqa: E402
import runner_worker  # noqa: E402


def has_pasp() -> bool:
    try:
        importlib.import_module("pasp")
        return True
    except Exception:
        return False


needs_pasp = pytest.mark.skipif(not has_pasp(), reason="dPASP is not installed")

EARTHQUAKE = """
0.7::burglary. 0.2::earthquake.
0.9::alarm :- burglary, earthquake.
0.8::alarm :- burglary, not earthquake.
0.1::alarm :- not burglary, earthquake.
#query(alarm | burglary, earthquake)
#query(alarm)
"""


# --------------------------------------------------------------------------
# Serialisation helpers
# --------------------------------------------------------------------------

def test_non_finite_bounds_are_json_safe():
    # JSON has no Infinity/NaN literals, so these must not reach json.dumps
    # as floats or the browser's JSON.parse rejects the whole response.
    assert runner_worker.jsonable(float("inf")) == "inf"
    assert runner_worker.jsonable(float("-inf")) == "-inf"
    assert runner_worker.jsonable(float("nan")) == "nan"
    assert runner_worker.jsonable(0.25) == 0.25
    json.dumps([runner_worker.jsonable(v) for v in (float("inf"), float("nan"), 0.5)])


def test_clean_output_drops_progress_bar():
    noisy = "Querying: \\\rQuerying: |\rQuerying: /\rreal output\n"
    assert dpasp_api.clean_output(noisy) == "real output"


def test_clean_output_drops_runner_notices():
    noisy = f"PyTorch not found!\n{runner_worker.OUTPUT_MARKER}\nhello\n"
    assert dpasp_api.clean_output(noisy) == "hello"


def test_clean_output_truncates(monkeypatch):
    monkeypatch.setattr(dpasp_api, "MAX_OUTPUT_CHARS", 50)
    out = dpasp_api.clean_output("x" * 500)
    assert out.endswith("output truncated ...")
    assert len(out) < 200


# --------------------------------------------------------------------------
# Mock target
# --------------------------------------------------------------------------

def test_mock_result_has_one_entry_per_query(monkeypatch):
    monkeypatch.setattr(dpasp_api, "IS_MOCK", True)
    result = dpasp_api.run_program(EARTHQUAKE)
    assert result["ok"]
    assert len(result["queries"]) == 2
    assert result["interval"] is True
    for entry in result["queries"]:
        assert 0.0 <= entry["lower"] <= entry["upper"] <= 1.0


def test_mock_maxent_is_a_point_value(monkeypatch):
    # The mock reads the directive textually, since there is no parser here.
    monkeypatch.setattr(dpasp_api, "IS_MOCK", True)
    result = dpasp_api.run_program("#semantics maxent.\n" + EARTHQUAKE)
    assert result["psem"] == "maxent"
    assert result["interval"] is False
    assert all(len(e["values"]) == 1 for e in result["queries"])


# --------------------------------------------------------------------------
# Real inference
# --------------------------------------------------------------------------

@needs_pasp
def test_credal_bounds_match_the_published_values():
    result = dpasp_api.run_program(EARTHQUAKE)
    assert result["ok"], result["error"]
    assert result["interval"] is True

    first = result["queries"][0]
    assert "burglary" in first["query"] and "earthquake" in first["query"]
    assert first["lower"] == pytest.approx(0.9, abs=1e-9)
    assert first["upper"] == pytest.approx(0.9, abs=1e-9)
    assert result["queries"][1]["lower"] == pytest.approx(0.58, abs=1e-9)


@needs_pasp
def test_maxent_returns_a_single_value_per_query():
    result = dpasp_api.run_program("#semantics maxent.\n" + EARTHQUAKE)
    assert result["ok"], result["error"]
    assert result["interval"] is False
    assert [len(e["values"]) for e in result["queries"]] == [1, 1]


@needs_pasp
def test_credal_bounds_can_differ():
    # Two stable models for the disjunction, so P(b) is only bounded.
    result = dpasp_api.run_program("0.5::a.\nb;c :- a.\n#query(b)\n")
    entry = result["queries"][0]
    assert entry["lower"] == pytest.approx(0.0)
    assert entry["upper"] == pytest.approx(0.5)


@needs_pasp
def test_the_semantics_directive_decides():
    # The only way to ask for max-entropy: there is no longer a request field
    # for it, because dPASP reads the program's directive regardless.
    result = dpasp_api.run_program("#semantics maxent.\n0.5::a.\nb;c :- a.\n#query(b)\n")
    assert result["psem"] == "maxent"
    assert result["interval"] is False


@needs_pasp
def test_the_logic_semantics_is_reported_from_the_program():
    # Reported, not echoed: `program.semantics` after parsing, so it reflects
    # the directive rather than anything the caller asked for.
    plain = dpasp_api.run_program("0.5::a.\n#query(a)\n")
    assert plain["sem"] == "stable"

    lstable = dpasp_api.run_program("#semantics lstable.\n0.5::a.\n#query(a)\n")
    assert lstable["sem"] == "lstable", lstable["error"]


@needs_pasp
def test_both_halves_of_the_directive_are_reported():
    result = dpasp_api.run_program(
        "#semantics lstable, maxent.\n0.5::a.\n#query(a)\n"
    )
    assert (result["sem"], result["psem"]) == ("lstable", "maxent"), result["error"]


@needs_pasp
def test_variable_queries_are_grounded_and_named():
    result = dpasp_api.run_program(
        "#semantics maxent.\n0.5::e(1). 0.5::e(2).\nf(X) :- e(X).\n#query(f(X))\n"
    )
    assert result["ok"], result["error"]
    names = [e["query"] for e in result["queries"]]
    assert len(names) == 2
    assert any("f(1)" in n for n in names) and any("f(2)" in n for n in names)


@needs_pasp
def test_a_syntax_error_reports_a_position():
    result = dpasp_api.run_program("0.7::burglary\n#query(burglary)\n")
    assert result["ok"] is False
    assert result["error"]["kind"] == "parse"
    assert result["error"]["line"] == 2
    assert result["error"]["column"] == 1


@needs_pasp
def test_a_program_without_queries_still_succeeds():
    result = dpasp_api.run_program("0.5::a.\n")
    assert result["ok"] is True
    assert result["queries"] == []


@needs_pasp
def test_a_runaway_program_is_stopped(monkeypatch):
    # Exact inference enumerates every total choice, so 30 probabilistic facts
    # is already 2^30 models: it cannot finish inside the deadline.
    monkeypatch.setattr(dpasp_api, "RUN_TIMEOUT_S", 3.0)
    facts = "\n".join(f"0.5::p{i}." for i in range(30))
    body = ", ".join(f"p{i}" for i in range(30))
    result = dpasp_api.run_program(f"{facts}\nq :- {body}.\n#query(q)\n")
    assert result["ok"] is False
    assert result["error"]["kind"] == "timeout"


@needs_pasp
def test_the_worker_is_a_separate_process():
    # The parent must not import pasp: inference has to be killable, and its
    # C-level stdout must not be the web server's.
    probe = (
        "import sys, dpasp_api; "
        "dpasp_api.run_program('0.5::a.\\n#query(a)\\n'); "
        "print('pasp' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip().endswith("False"), out.stdout + out.stderr


# --------------------------------------------------------------------------
# Resource limits
#
# These exist because of two real failures, both of which showed up as
# "<some library>.so: failed to map segment from shared object" while the
# runner was loading dPASP:
#
#   1. the limit was originally RLIMIT_AS, which bounds address space and so
#      bounds file-backed library mappings (broke `import torch`);
#   2. RLIMIT_DATA was then applied *before* the imports, so the runtime's own
#      loading had to fit inside the user's budget. On x86_64, where pip
#      installs the CUDA build of torch, `import pasp` holds ~790 MB of data
#      mappings — most of a 1024 MB budget (broke `libc10_cuda.so`).
# --------------------------------------------------------------------------

def run_probe(body):
    """Run `body` in a fresh interpreter with runner_worker importable."""
    probe = "import sys; sys.path.insert(0, %r)\n%s" % (
        os.path.dirname(os.path.abspath(__file__)),
        body,
    )
    return subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)


def limits_in_child(mem_limit_mb):
    """Apply both limit sets in a fresh process and report the rlimits."""
    out = run_probe(
        "import json, resource, runner_worker\n"
        "runner_worker.apply_process_limits()\n"
        "runner_worker.apply_memory_limit(%d)\n"
        "print(json.dumps({"
        "'data': resource.getrlimit(resource.RLIMIT_DATA),"
        "'addr': resource.getrlimit(resource.RLIMIT_AS),"
        "'core': resource.getrlimit(resource.RLIMIT_CORE),"
        "'used': runner_worker.data_vm_bytes()}))" % mem_limit_mb
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_heap_is_capped_not_the_address_space():
    limits = limits_in_child(512)

    # The cap is the budget *plus* what the interpreter already holds, so it
    # is above the budget but not far above it.
    assert limits["data"][0] > 512 * 1024 * 1024
    assert limits["data"][0] == pytest.approx(
        limits["used"] + 512 * 1024 * 1024, abs=8 * 1024 * 1024
    )
    # The crux: bounding the address space breaks loading big shared
    # libraries, so it must be left alone.
    assert limits["addr"][0] == resource.RLIM_INFINITY


def test_the_baseline_is_measured_not_guessed():
    """`data_vm_bytes` must read a real figure; 0 would silently make the
    limit absolute again."""
    assert limits_in_child(512)["used"] > 1024 * 1024


def test_core_dumps_are_disabled():
    assert limits_in_child(512)["core"] == [0, 0]


def test_a_zero_limit_leaves_the_heap_alone():
    limits = limits_in_child(0)
    assert limits["data"][0] == resource.RLIM_INFINITY


def test_the_heap_cap_actually_bites():
    """A runaway allocation must fail, and fail as a clean MemoryError."""
    out = run_probe(
        "import runner_worker\n"
        "runner_worker.apply_memory_limit(256)\n"
        "try:\n"
        "    x = bytearray(2 * 1024 * 1024 * 1024)\n"
        "    print('ALLOCATED')\n"
        "except MemoryError:\n"
        "    print('MEMORYERROR')\n"
    )
    assert out.stdout.strip() == "MEMORYERROR", out.stdout + out.stderr


def test_the_budget_is_on_top_of_what_is_already_held():
    """The second regression, in miniature.

    The 200 MB buffer stands in for what importing dPASP costs (on x86_64
    with the CUDA torch build, ~790 MB). With an absolute limit, a 64 MB
    budget applied afterwards would be *below* what is already held and the
    next small allocation would fail — which is how loading a library came to
    fail with "failed to map segment from shared object". The budget has to
    be the program's allowance, not the process total.
    """
    out = run_probe(
        "import runner_worker\n"
        "runner_worker.apply_process_limits()\n"
        "held = bytearray(200 * 1024 * 1024)\n"
        "held[::4096] = b'x' * (len(held) // 4096)\n"
        "runner_worker.apply_memory_limit(64)\n"
        "try:\n"
        "    small = bytearray(32 * 1024 * 1024)\n"
        "    small[::4096] = b'x' * (len(small) // 4096)\n"
        "    print('WITHIN-BUDGET-OK')\n"
        "except MemoryError:\n"
        "    print('WITHIN-BUDGET-FAILED')\n"
        "try:\n"
        "    huge = bytearray(512 * 1024 * 1024)\n"
        "    huge[::4096] = b'x' * (len(huge) // 4096)\n"
        "    print('OVER-BUDGET-ALLOWED')\n"
        "except MemoryError:\n"
        "    print('OVER-BUDGET-REFUSED')\n"
    )
    assert out.stdout.split() == ["WITHIN-BUDGET-OK", "OVER-BUDGET-REFUSED"], (
        out.stdout + out.stderr
    )


def test_a_large_shared_library_still_loads_under_the_cap():
    """A big extension must load even with a cap already in force.

    numpy stands in for torch — it is a dPASP dependency, and importing it
    maps about 137 MB of address space while needing far less heap. The cap
    here is deliberately below that virtual size, so this test fails if the
    limit is ever switched back to RLIMIT_AS, which is what produced

        libtorch_python.so: failed to map segment from shared object
    """
    out = run_probe(
        "import runner_worker\n"
        "runner_worker.apply_memory_limit(128)\n"
        "import numpy; print('IMPORTED', numpy.__version__)\n"
    )
    assert out.stdout.startswith("IMPORTED"), out.stdout + out.stderr


@needs_pasp
def test_dpasp_imports_before_any_heap_cap_is_applied():
    """The worker's actual order: imports first, budget afterwards.

    dPASP imports torch at import time (`pasp/program.py`), and on x86_64
    that is the CUDA build. Nothing may bound that.
    """
    source = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "runner_worker.py")).read()
    body = source.split("def main()", 1)[1]
    import_pos = body.index("import pasp")
    limit_pos = body.index("apply_memory_limit(")
    assert import_pos < limit_pos, "the heap cap must be applied after importing dPASP"


@needs_pasp
def test_dpasp_imports_under_the_cap():
    """Belt and braces: even with the budget already in force, dPASP loads."""
    out = run_probe(
        "import runner_worker\n"
        "runner_worker.apply_memory_limit(%d)\n"
        "import pasp; print('IMPORTED', pasp.__version__)\n"
        % runner_worker.DEFAULT_MEM_LIMIT_MB
    )
    assert "IMPORTED" in out.stdout, out.stdout + out.stderr


@needs_pasp
def test_a_real_run_succeeds_under_the_default_cap():
    """End to end at the shipped default, the configuration users actually get."""
    result = dpasp_api.run_program(EARTHQUAKE)
    assert result["ok"] is True, result["error"]
    assert result["queries"][1]["lower"] == pytest.approx(0.58, abs=1e-9)


# --------------------------------------------------------------------------
# The run deadline
# --------------------------------------------------------------------------

def test_the_default_deadline_is_five_minutes():
    assert dpasp_api.RUN_TIMEOUT_S == 300.0


def test_the_deadline_is_configurable(monkeypatch):
    # Set on the runner container by containerManager.runnerEnvironment,
    # which forwards it from Compose.
    monkeypatch.setenv("DPASP_RUN_TIMEOUT", "42.5")
    importlib.reload(dpasp_api)
    try:
        assert dpasp_api.RUN_TIMEOUT_S == 42.5
    finally:
        monkeypatch.delenv("DPASP_RUN_TIMEOUT")
        importlib.reload(dpasp_api)
    assert dpasp_api.RUN_TIMEOUT_S == 300.0


@needs_pasp
def test_the_timeout_message_quotes_the_configured_deadline(monkeypatch):
    monkeypatch.setattr(dpasp_api, "RUN_TIMEOUT_S", 2.0)
    facts = "\n".join(f"0.5::p{i}." for i in range(30))
    body = ", ".join(f"p{i}" for i in range(30))
    result = dpasp_api.run_program(f"{facts}\nq :- {body}.\n#query(q)\n")

    assert result["error"]["kind"] == "timeout"
    assert "2 seconds" in result["error"]["message"]


def test_clean_output_drops_the_learning_bar():
    # The learning bar writes `Learning [ ... ]`, not `Learning: ...`. Matching
    # only the colon form let it leak into the output pane.
    noisy = "Learning [        ] ETA: 0h00m00s | LL=0.00000\nreal output\n"
    assert dpasp_api.clean_output(noisy) == "real output"
