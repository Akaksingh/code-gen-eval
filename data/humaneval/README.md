# HumanEval drop-in

The harness expects a dataset directory with a `problems.jsonl`, one object per line:

```json
{"task_id": "...", "prompt": "...", "entry_point": "...", "test": "...", "tags": [], "canonical_solution": "..."}
```

This is **exactly HumanEval's schema**, so converting it is a copy:

```python
# pip install human-eval   (or read the jsonl from the openai/human-eval repo)
from human_eval.data import read_problems
import json
probs = read_problems()  # dict of task_id -> {prompt, entry_point, test, canonical_solution, ...}
with open("problems.jsonl", "w", encoding="utf-8") as f:
    for tid, p in probs.items():
        f.write(json.dumps({
            "task_id": tid,
            "prompt": p["prompt"],
            "entry_point": p["entry_point"],
            "test": p["test"],
            "tags": [],
            "canonical_solution": p["canonical_solution"],
        }) + "\n")
```

Then: `python -m harness.run --dataset humaneval --provider anthropic`

**MBPP** works the same way — map its `text`→a prompt, `code`→`canonical_solution`,
and `test_list`→a `check` function.

Notes:
- Record the exact benchmark version/commit in your run notes — reproducibility is a
  word you earn.
- Keep a hold-out slice you never look at while tuning prompts, so your final number
  isn't inflated by few-shot examples drawn from the test set.
- HumanEval's `test` code is trusted (it ships with the benchmark). The sandbox still
  runs everything in isolation — see `harness/sandbox.py`.
