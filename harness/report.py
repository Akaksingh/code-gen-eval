"""Aggregate JSONL run logs into the table that makes the repo.

    python -m harness.report                 # all runs in runs/
    python -m harness.report runs/foo.jsonl  # specific run(s)

Per run: pass@1, valid-run rate (did it execute without crashing?), $/100 problems,
p50/p95 latency, and an error taxonomy. The grid (2-3 prompts x 2 models side by
side) falls out of running several configs and letting this list them all."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .config import load_config, resolve

try:
    from tabulate import tabulate
except ImportError:
    tabulate = None


def _percentile(xs: list[float], q: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarize(log_path: Path) -> dict | None:
    header = None
    rows = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("_type") == "run_header":
                header = rec
            elif rec.get("_type") == "problem":
                rows.append(rec)
    if not rows:
        return None

    n = len(rows)
    n_pass = sum(1 for e in rows if e["passed"])
    # "valid-run": the code at least executed to completion without crashing.
    # (status "fail" means it ran but asserted wrong; "error"/"timeout" means it didn't.)
    n_valid = sum(1 for e in rows if e["status"] in ("pass", "fail"))
    total_cost = sum(e["cost_usd"] for e in rows)
    latencies = [e["latency_s"] for e in rows]
    errors = Counter(e["error_bucket"] for e in rows if e["error_bucket"])

    return {
        "model": (header or {}).get("model", "?"),
        "prompt": (header or {}).get("prompt_variant", "?"),
        "n": n,
        "pass_at_1": n_pass / n,
        "valid_run": n_valid / n,
        "cost_per_100": total_cost / n * 100,
        "p50": _percentile(latencies, 0.50),
        "p95": _percentile(latencies, 0.95),
        "errors": dict(errors.most_common()),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Aggregate eval run logs into a table.")
    p.add_argument("logs", nargs="*", help="specific .jsonl logs (default: all in runs/)")
    a = p.parse_args(argv)

    if a.logs:
        paths = [Path(x) for x in a.logs]
    else:
        cfg = load_config()
        paths = sorted(resolve(cfg, cfg["runs_dir"]).glob("*.jsonl"))

    summaries = [s for pth in paths if (s := summarize(pth))]
    if not summaries:
        print("No run logs found. Run:  python -m harness.run --dataset golden --provider mock")
        return 1

    rows = [[
        s["prompt"], s["model"], s["n"],
        f"{s['pass_at_1']:.1%}", f"{s['valid_run']:.1%}",
        f"${s['cost_per_100']:.2f}", f"{s['p50']:.2f}s", f"{s['p95']:.2f}s",
    ] for s in summaries]
    headers = ["prompt", "model", "n", "pass@1", "valid_run", "$/100", "p50", "p95"]

    print()
    if tabulate:
        print(tabulate(rows, headers=headers, tablefmt="github"))
    else:
        print("\t".join(headers))
        for r in rows:
            print("\t".join(str(c) for c in r))

    print("\nError taxonomy (per run):")
    for s in summaries:
        if s["errors"]:
            parts = ", ".join(f"{k}={v}" for k, v in s["errors"].items())
            print(f"  {s['prompt']} / {s['model']}: {parts}")
        else:
            print(f"  {s['prompt']} / {s['model']}: (no failures)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
