# Error analysis

The run logs in `runs/*.jsonl` are the raw material. Each `problem` line records the
task_id, tags, generated code, pass/fail, the failure `status`
(pass/fail/timeout/error), the `detail` (the exception tail), and the `error_bucket`.

A notebook here should:

1. Load the latest run's JSONL into a DataFrame.
2. Group failures by `error_bucket` and by `tags` — e.g. "we fail most `string`
   problems with `wrong_answer`, but `array` problems crash with `bad_indexing`".
3. Read the 5 most interesting failures' generated code next to the spec.

That breakdown is the deliverable: it points at a specific weakness, and **that
weakness becomes Project 2's thesis** (e.g. "the model crashes on edge cases it
didn't test → an agentic self-repair loop that runs the tests and fixes failures
should recover them").

Quick start (`pip install jupyter pandas`, commented in requirements.txt):

```python
import json, pandas as pd, glob
latest = sorted(glob.glob("../runs/*.jsonl"))[-1]
rows = [json.loads(l) for l in open(latest, encoding="utf-8")]
df = pd.DataFrame([r for r in rows if r.get("_type") == "problem"])
df.groupby("error_bucket").size().sort_values(ascending=False)
```
