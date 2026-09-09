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
    result = dpasp_api.run_program("stable", "credal", EARTHQUAKE)
    assert result["ok"]
    assert len(result["queries"]) == 2
    assert result["interval"] is True
    for entry in result["queries"]:
        assert 0.0 <= entry["lower"] <= entry["upper"] <= 1.0


def test_mock_maxent_is_a_point_value(monkeypatch):
    monkeypatch.setattr(dpasp_api, "IS_MOCK", True)
    result = dpasp_api.run_program("stable", "maxent", EARTHQUAKE)
    assert result["interval"] is False
    assert all(len(e["values"]) == 1 for e in result["queries"])


# --------------------------------------------------------------------------
# Real inference
# --------------------------------------------------------------------------

@needs_pasp
def test_credal_bounds_match_the_published_values():
    result = dpasp_api.run_program("stable", "credal", EARTHQUAKE)
    assert result["ok"], result["error"]
    assert result["interval"] is True

    first = result["queries"][0]
    assert "burglary" in first["query"] and "earthquake" in first["query"]
    assert first["lower"] == pytest.approx(0.9, abs=1e-9)
    assert first["upper"] == pytest.approx(0.9, abs=1e-9)
    assert result["queries"][1]["lower"] == pytest.approx(0.58, abs=1e-9)


@needs_pasp
def test_maxent_returns_a_single_value_per_query():
    result = dpasp_api.run_program("stable", "maxent", EARTHQUAKE)
    assert result["ok"], result["error"]
    assert result["interval"] is False
    assert [len(e["values"]) for e in result["queries"]] == [1, 1]


@needs_pasp
def test_credal_bounds_can_differ():
    # Two stable models for the disjunction, so P(b) is only bounded.
    result = dpasp_api.run_program("stable", "credal", "0.5::a.\nb;c :- a.\n#query(b)\n")
    entry = result["queries"][0]
    assert entry["lower"] == pytest.approx(0.0)
    assert entry["upper"] == pytest.approx(0.5)


@needs_pasp
def test_a_semantics_directive_overrides_the_request():
    # The `pasp` CLI lets the program's own directive win; so do we.
    result = dpasp_api.run_program(
        "stable", "credal", "#semantics maxent.\n0.5::a.\nb;c :- a.\n#query(b)\n"
    )
    assert result["psem"] == "maxent"
    assert result["interval"] is False


@needs_pasp
def test_variable_queries_are_grounded_and_named():
    result = dpasp_api.run_program(
        "stable", "maxent", "0.5::e(1). 0.5::e(2).\nf(X) :- e(X).\n#query(f(X))\n"
    )
    assert result["ok"], result["error"]
    names = [e["query"] for e in result["queries"]]
    assert len(names) == 2
    assert any("f(1)" in n for n in names) and any("f(2)" in n for n in names)


@needs_pasp
def test_a_syntax_error_reports_a_position():
    result = dpasp_api.run_program("stable", "credal", "0.7::burglary\n#query(burglary)\n")
    assert result["ok"] is False
    assert result["error"]["kind"] == "parse"
    assert result["error"]["line"] == 2
    assert result["error"]["column"] == 1


@needs_pasp
def test_a_program_without_queries_still_succeeds():
    result = dpasp_api.run_program("stable", "credal", "0.5::a.\n")
    assert result["ok"] is True
    assert result["queries"] == []


@needs_pasp
def test_a_runaway_program_is_stopped(monkeypatch):
    # Exact inference enumerates every total choice, so 30 probabilistic facts
    # is already 2^30 models: it cannot finish inside the deadline.
    monkeypatch.setattr(dpasp_api, "RUN_TIMEOUT_S", 3.0)
    facts = "\n".join(f"0.5::p{i}." for i in range(30))
    body = ", ".join(f"p{i}" for i in range(30))
    result = dpasp_api.run_program("stable", "credal", f"{facts}\nq :- {body}.\n#query(q)\n")
    assert result["ok"] is False
    assert result["error"]["kind"] == "timeout"


@needs_pasp
def test_the_worker_is_a_separate_process():
    # The parent must not import pasp: inference has to be killable, and its
    # C-level stdout must not be the web server's.
    probe = (
        "import sys, dpasp_api; "
        "dpasp_api.run_program('stable','credal','0.5::a.\\n#query(a)\\n'); "
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
# These exist because of a real failure: the limit was originally RLIMIT_AS,
# which broke `import torch` inside the runner with
# "libtorch_python.so: failed to map segment from shared object".
# --------------------------------------------------------------------------

def limits_in_child(mem_limit_mb):
    """Run apply_limits in a fresh process and report the resulting rlimits."""
    probe = (
        "import json, resource, sys;"
        "sys.path.insert(0, %r);"
        "import runner_worker;"
        "runner_worker.apply_limits(%d);"
        "print(json.dumps({"
        "'data': resource.getrlimit(resource.RLIMIT_DATA),"
        "'addr': resource.getrlimit(resource.RLIMIT_AS),"
        "'core': resource.getrlimit(resource.RLIMIT_CORE)}))"
        % (os.path.dirname(os.path.abspath(__file__)), mem_limit_mb)
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_heap_is_capped_not_the_address_space():
    limits = limits_in_child(512)

    assert limits["data"][0] == 512 * 1024 * 1024
    # The crux: bounding the address space breaks loading big shared
    # libraries, so it must be left alone.
    assert limits["addr"][0] == resource.RLIM_INFINITY


def test_core_dumps_are_disabled():
    assert limits_in_child(512)["core"] == [0, 0]


def test_a_zero_limit_leaves_the_heap_alone():
    limits = limits_in_child(0)
    assert limits["data"][0] == resource.RLIM_INFINITY


def test_the_heap_cap_actually_bites():
    """A runaway allocation must fail, and fail as a clean MemoryError."""
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "import runner_worker; runner_worker.apply_limits(256);"
        "\ntry:\n"
        "    x = bytearray(1024 * 1024 * 1024)\n"
        "    print('ALLOCATED')\n"
        "except MemoryError:\n"
        "    print('MEMORYERROR')\n" % os.path.dirname(os.path.abspath(__file__))
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert out.stdout.strip() == "MEMORYERROR", out.stdout + out.stderr


def test_a_large_shared_library_still_loads_under_the_cap():
    """The regression itself: a big extension must load despite the cap.

    numpy stands in for torch — it is a dPASP dependency, and importing it
    maps about 137 MB of address space while needing far less heap. The cap
    here is deliberately below that virtual size, so this test fails if the
    limit is ever switched back to RLIMIT_AS, which is what produced

        libtorch_python.so: failed to map segment from shared object
    """
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "import runner_worker; runner_worker.apply_limits(128);"
        "import numpy; print('IMPORTED', numpy.__version__)"
        % os.path.dirname(os.path.abspath(__file__))
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert out.stdout.startswith("IMPORTED"), out.stdout + out.stderr


@needs_pasp
def test_dpasp_imports_under_the_cap():
    """dPASP itself, which imports torch when it is installed."""
    probe = (
        "import sys; sys.path.insert(0, %r);"
        "import runner_worker; runner_worker.apply_limits(%d);"
        "import pasp; print('IMPORTED', pasp.__version__)"
        % (os.path.dirname(os.path.abspath(__file__)), runner_worker.DEFAULT_MEM_LIMIT_MB)
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    assert "IMPORTED" in out.stdout, out.stdout + out.stderr


@needs_pasp
def test_a_real_run_succeeds_under_the_default_cap():
    """End to end at the shipped default, the configuration users actually get."""
    result = dpasp_api.run_program("stable", "credal", EARTHQUAKE)
    assert result["ok"] is True, result["error"]
    assert result["queries"][1]["lower"] == pytest.approx(0.58, abs=1e-9)
