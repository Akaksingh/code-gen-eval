"""Run untrusted, model-generated code safely and report whether its tests pass.

This is the oracle for the whole eval, and the part that makes code-gen a real
engineering project rather than a notebook demo. Generated code is hostile by
assumption: it may loop forever, print gigabytes, try to read your files, or import
the network. The runner's job is to let it run its tests and nothing else.

Isolation measures (defense in depth; none is sufficient alone):
  - separate process: each candidate runs in a fresh `python -I` subprocess, so a
    crash or `sys.exit` can't take the harness down, and -I ignores env/user site.
  - wall-clock timeout: the subprocess is killed (whole tree) if it exceeds the
    limit, catching infinite loops.
  - throwaway CWD: it runs in a fresh temp dir that's deleted afterwards, so files
    it writes don't litter the repo.
  - scrubbed environment: no inherited env vars (no API keys leak into the child).
  - output caps: stdout/stderr are truncated, so a noisy program can't exhaust memory.
  - a prelude that disables the most obvious escape hatches (network sockets,
    subprocess spawning) inside the child.

NOTE: this is process-level isolation, not a security boundary against a determined
adversary (that needs containers/gVisor/seccomp — a known, documented limitation,
and exactly the kind of thing to say in the README). It is appropriate for
evaluating benchmark solutions, which is what we're doing.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass


@dataclass
class RunOutcome:
    passed: bool            # did the test suite pass (exit 0)?
    status: str             # "pass" | "fail" | "timeout" | "error"
    detail: str             # exception/traceback tail or error reason, for the taxonomy
    stdout: str
    stderr: str


# Injected at the top of every candidate module. Best-effort lockdown of the most
# common escape hatches so a buggy/hostile solution can't phone home or spawn shells.
_PRELUDE = """\
import builtins as _b, os as _os
# Block process spawning.
_os.system = lambda *a, **k: (_ for _ in ()).throw(PermissionError("os.system disabled in sandbox"))
try:
    import subprocess as _sp
    def _blocked(*a, **k):
        raise PermissionError("subprocess disabled in sandbox")
    _sp.Popen = _blocked
    _sp.run = _blocked
    _sp.call = _blocked
except Exception:
    pass
# Block network at the socket layer.
try:
    import socket as _s
    def _nosock(*a, **k):
        raise PermissionError("network disabled in sandbox")
    _s.socket = _nosock
    _s.create_connection = _nosock
except Exception:
    pass
"""


def _build_program(candidate_code: str, test_code: str, entry_point: str) -> str:
    """Assemble the single module the subprocess runs: prelude + candidate + test.

    The test code defines `check(candidate)` and calls it (HumanEval convention); we
    append a call that passes the generated `entry_point` function into the tests.
    If `check` isn't defined (some suites just run asserts inline), the test code's
    own top-level statements still execute."""
    return (
        _PRELUDE
        + "\n# ---- candidate (model-generated) ----\n"
        + candidate_code
        + "\n\n# ---- tests (trusted, from the dataset) ----\n"
        + test_code
        + f"\n\n# ---- invoke ----\n"
        + f"if 'check' in dir():\n"
        + f"    check({entry_point})\n"
    )


def _truncate(b: bytes, cap: int) -> str:
    s = b.decode("utf-8", errors="replace")
    if len(b) > cap:
        return s[:cap] + f"\n...[truncated, {len(b)} bytes]"
    return s


def run_tests(candidate_code: str, test_code: str, entry_point: str, *,
              timeout_s: float = 10.0, max_output_bytes: int = 65536) -> RunOutcome:
    """Run `candidate_code` against `test_code` in an isolated subprocess."""
    program = _build_program(candidate_code, test_code, entry_point)

    with tempfile.TemporaryDirectory(prefix="cgeval_") as workdir:
        script = os.path.join(workdir, "prog.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(program)

        # -I: isolated mode (ignores env PYTHON*, user site, and CWD on sys.path besides
        # the script dir). Minimal env so no secrets reach the child.
        env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "prog.py"],
                cwd=workdir,
                env=env,
                capture_output=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as e:
            return RunOutcome(
                passed=False, status="timeout",
                detail=f"exceeded {timeout_s}s wall-clock",
                stdout=_truncate(e.stdout or b"", max_output_bytes),
                stderr=_truncate(e.stderr or b"", max_output_bytes),
            )

        stdout = _truncate(proc.stdout, max_output_bytes)
        stderr = _truncate(proc.stderr, max_output_bytes)
        if proc.returncode == 0:
            return RunOutcome(True, "pass", "", stdout, stderr)

        # Nonzero exit: distinguish an assertion failure (wrong answer) from a crash
        # (syntax error, exception, etc.) by sniffing the stderr tail.
        tail = stderr.strip().splitlines()[-1] if stderr.strip() else "(no stderr)"
        status = "fail" if "AssertionError" in stderr else "error"
        return RunOutcome(False, status, tail, stdout, stderr)
