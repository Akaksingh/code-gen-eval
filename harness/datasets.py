"""Load code-generation problems from a dataset directory.

A dataset directory contains:
  problems.jsonl — one problem per line:
    {
      "task_id":    "golden/two_sum",      # unique id
      "prompt":     "def two_sum(...):\\n    \\"\\"\\"...\\"\\"\\"\\n",  # the spec the model completes
      "entry_point":"two_sum",             # the function the tests call
      "test":       "def check(candidate): assert candidate([2,7],9)==[0,1]\\ncheck(two_sum)",
      "tags":       ["array", "hashmap"],  # gives error analysis teeth
      "canonical_solution": "    ..."       # optional reference body (used by mock)
    }

This is exactly HumanEval's shape (task_id / prompt / entry_point / test /
canonical_solution), so pointing the harness at HumanEval is a drop-in. See
data/humaneval/README.md."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Problem:
    task_id: str
    prompt: str                 # the function signature + docstring the model completes
    entry_point: str            # the function name the test harness calls
    test: str                   # test code that defines check(candidate) and runs it
    tags: list[str] = field(default_factory=list)
    canonical_solution: str = ""  # reference body (indented), for the mock provider


def load_problems(dataset_dir: str | Path, limit: int | None = None) -> list[Problem]:
    dataset_dir = Path(dataset_dir)
    jsonl = dataset_dir / "problems.jsonl"
    if not jsonl.exists():
        raise FileNotFoundError(
            f"No problems.jsonl in {dataset_dir}. "
            f"For the golden set, run: python -m harness.build_golden_set"
        )
    out: list[Problem] = []
    with open(jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            out.append(Problem(
                task_id=rec["task_id"],
                prompt=rec["prompt"],
                entry_point=rec["entry_point"],
                test=rec["test"],
                tags=rec.get("tags", []),
                canonical_solution=rec.get("canonical_solution", ""),
            ))
            if limit is not None and len(out) >= limit:
                break
    return out
