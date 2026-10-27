# code-gen-eval

An execution-based evaluation harness for LLM **code generation**. Give it
`(spec, tests)` problems; it prompts an LLM to write the code, runs the generated
code against a hidden test suite **in a sandbox**, and scores pass@1 — with cost and
latency logged per call.

> **Project 1 of a 3-project arc.** This is the *ruler*. Project 2 (an agentic
> system that writes code and iterates against the tests) reuses this harness to
> prove its self-repair loop actually raised pass@1 — measured, not claimed.

The résumé line both projects earn:

> Built an execution-based evaluation harness for LLM code generation — sandboxed
> test execution, pass@1 / cost / latency / error taxonomy — then used it to drive a
> self-repairing generation system from ~X% to ~Y% pass@1 on held-out problems.

## Results

<!-- Replace with your real measured grid once you've run it. -->

| Prompt variant | Model | pass@1 | valid-run | $/100 | p50 | p95 |
|----------------|-------|-------:|----------:|------:|----:|----:|
| _(run the harness and paste the table here)_ | | | | | | |

## What I learned

<!-- One paragraph. Lead with the decision and the number, not the install steps. -->

## Quickstart

```powershell
# 1. Create the env and install pins (Windows / PowerShell)
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Build the 10-problem hand-written "golden" set (self-tests every reference)
python -m harness.build_golden_set

# 3. Run the whole eval on the golden set with the mock provider (no API key needed)
python -m harness.run --dataset golden --provider mock

# 4. See the aggregate table
python -m harness.report
```

On macOS/Linux, swap step 1 for `python3 -m venv .venv && source .venv/bin/activate`.

Use a real model by setting the provider and a key:

```powershell
copy .env.example .env    # then edit ANTHROPIC_API_KEY
python -m harness.run --dataset golden --provider anthropic
```

Or a local model: install [Ollama](https://ollama.com), `ollama pull qwen2.5-coder`,
then `python -m harness.run --dataset golden --provider ollama`.

## The sandbox (why this isn't a notebook demo)

Running untrusted, model-generated code is the real engineering problem here, and
[`harness/sandbox.py`](harness/sandbox.py) is where the project earns its keep. Every
candidate runs in a **fresh `python -I` subprocess** with:

- a **wall-clock timeout** (kills infinite loops),
- a **throwaway temp working directory** (deleted after; no litter, no reading the repo),
- a **scrubbed environment** (no inherited vars, so no API keys leak into the child),
- **stdout/stderr caps** (a noisy program can't exhaust memory), and
- a **prelude that disables** `os.system`, `subprocess`, and network sockets inside the child.

This is process-level isolation, not a hardened security boundary against a
determined adversary — that would need containers + seccomp/gVisor. Stating that
limitation honestly is part of the point: it's appropriate for scoring benchmark
solutions, and knowing the difference is the senior read.

## Metrics, and why each one is here

| Metric | Definition | Why |
|--------|------------|-----|
| **pass@1** | % of problems whose generated code passes the hidden tests on the first try | The headline. Objective — a test suite is the oracle, no LLM-judge hand-waving. |
| Valid-run rate | % of generations that execute without crashing (incl. wrong answers) | Separates "wrong logic" from "didn't even run" — a different failure to fix. |
| Cost / 100 problems | Token cost, normalized | Turns accuracy into an economic decision — reads as production-minded. |
| Latency p50 / p95 | Median and tail wall-clock per generation | Tail latency is what users feel. |
| Error taxonomy | Counts by failure type: wrong_answer, syntax_error, timeout, bad_indexing, … | The breakdown is the insight — it tells Project 2 what to fix. |

## Layout

```
code-gen-eval/
├─ README.md
├─ config.yaml            # models, temps, sandbox limits, dataset paths
├─ requirements.txt       # pinned
├─ .env.example
├─ harness/
│  ├─ run.py              # the core loop (python -m harness.run)
│  ├─ llm.py              # provider interface: mock / anthropic / ollama
│  ├─ prompts.py          # prompt variants + code extractor
│  ├─ sandbox.py          # run untrusted code safely; the test oracle
│  ├─ datasets.py         # load (spec, tests) problems (HumanEval shape)
│  ├─ report.py           # aggregate JSONL runs → table
│  └─ build_golden_set.py # the 10-problem hand-written set
├─ data/
│  ├─ golden/             # hand-written problems.jsonl (debug the harness here)
│  └─ humaneval/          # drop a HumanEval slice here (see its README)
├─ runs/                  # JSONL logs (gitignored)
└─ notebooks/             # error analysis
```

## Data

- **golden** — 10 problems you fully understand (strings, math, lists, edge cases).
  Build the loop correct here before trusting a big benchmark.
- **HumanEval / MBPP** — the recognized public benchmarks. The golden set uses
  HumanEval's exact schema, so pointing the harness at HumanEval is a drop-in; see
  [data/humaneval/README.md](data/humaneval/README.md).

Keep a hold-out slice you never look at while tuning prompts. Report final numbers
on it once.
