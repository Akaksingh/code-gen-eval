"""The core loop. The whole project in one readable file.

    for p in load_problems(dataset, limit=N):
        prompt      = build_prompt(variant, p.prompt)
        text, usage = llm.generate(prompt)
        code        = extract_code(text, p.prompt, p.entry_point)
        outcome     = run_tests(code, p.test, p.entry_point)   # sandboxed
        log(p, code, outcome, usage)                           # one JSONL line

The headline metric is pass@1: the fraction of problems whose generated code passes
the hidden test suite on the first try. Every line here is reused by Project 2 (an
agentic system that iterates against the tests) — the harness is the ruler that
proves Project 2's iteration actually helped.

Usage:
    python -m harness.run --dataset golden --provider mock
    python -m harness.run --dataset golden --provider anthropic --prompt cot --limit 50
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import llm as llm_mod
from .config import load_config, resolve
from .datasets import load_problems
from .prompts import build_prompt, extract_code
from .sandbox import run_tests


def classify_failure(outcome_status: str, detail: str) -> str:
    """Bucket a failure for the error taxonomy — the insight that tells Project 2
    what to fix."""
    if outcome_status == "timeout":
        return "timeout"                       # infinite loop / pathological complexity
    d = detail.lower()
    if outcome_status == "fail":
        return "wrong_answer"                  # ran fine, tests asserted otherwise
    # status == "error": the code crashed
    if "syntaxerror" in d or "indentationerror" in d:
        return "syntax_error"
    if "nameerror" in d:
        return "undefined_name"                # used a name it never defined/imported
    if "typeerror" in d:
        return "type_error"
    if "indexerror" in d or "keyerror" in d:
        return "bad_indexing"
    if "recursionerror" in d:
        return "runaway_recursion"
    return "other_runtime_error"


def run(dataset: str, provider: str | None, prompt_variant: str | None,
        limit: int | None, config_path: str | None) -> Path:
    cfg = load_config(config_path)
    provider = provider or cfg["provider"]
    prompt_variant = prompt_variant or cfg["prompt"]
    dataset_dir = resolve(cfg, cfg["datasets"][dataset]["dir"])
    sbox = cfg.get("sandbox", {})
    timeout_s = float(sbox.get("timeout_s", 10))
    max_out = int(sbox.get("max_output_bytes", 65536))

    client = llm_mod.get_client(cfg, provider)
    problems = load_problems(dataset_dir, limit=limit)

    runs_dir = resolve(cfg, cfg["runs_dir"])
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = runs_dir / f"{stamp}_{dataset}_{provider}_{prompt_variant}.jsonl"

    header = {
        "_type": "run_header",
        "timestamp": stamp,
        "dataset": dataset,
        "dataset_dir": str(dataset_dir),
        "provider": provider,
        "model": client.model,
        "prompt_variant": prompt_variant,
        "n_problems": len(problems),
        "sandbox": {"timeout_s": timeout_s, "max_output_bytes": max_out},
    }

    n_pass = 0
    with open(log_path, "w", encoding="utf-8") as logf:
        logf.write(json.dumps(header) + "\n")
        for i, p in enumerate(problems, 1):
            prompt = build_prompt(prompt_variant, p.prompt)

            # Mock side channel: let the fake provider complete from the reference.
            # Real providers have no set_reference and never see the solution.
            if hasattr(client, "set_reference"):
                client.set_reference(p.prompt, p.canonical_solution)

            try:
                gen = client.generate(prompt)
            except Exception as e:  # provider/network failure shouldn't kill the run
                gen = llm_mod.Generation(text="", model=client.model,
                                         raw={"provider_error": repr(e)})

            code = extract_code(gen.text, p.prompt, p.entry_point)
            outcome = run_tests(code, p.test, p.entry_point,
                                timeout_s=timeout_s, max_output_bytes=max_out)

            if outcome.passed:
                n_pass += 1
            bucket = None if outcome.passed else classify_failure(outcome.status, outcome.detail)

            logf.write(json.dumps({
                "_type": "problem",
                "i": i,
                "task_id": p.task_id,
                "entry_point": p.entry_point,
                "tags": p.tags,
                "generated_code": code,
                "raw_output": gen.text if gen.text != code else None,
                "passed": outcome.passed,
                "status": outcome.status,       # pass | fail | timeout | error
                "detail": outcome.detail,
                "error_bucket": bucket,
                "input_tokens": gen.input_tokens,
                "output_tokens": gen.output_tokens,
                "cost_usd": gen.cost_usd,
                "latency_s": round(gen.latency_s, 4),
            }) + "\n")

            mark = "PASS" if outcome.passed else f"{outcome.status.upper():<7}"
            print(f"[{i:>3}/{len(problems)}] {mark}  {p.task_id}")

    acc = n_pass / len(problems) if problems else 0.0
    print(f"\npass@1: {n_pass}/{len(problems)} = {acc:.1%}")
    print(f"Run log: {log_path}")
    print(f"Aggregate it with:  python -m harness.report")
    return log_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the code-generation eval harness.")
    p.add_argument("--dataset", default="golden", help="dataset name in config.yaml")
    p.add_argument("--provider", default=None, help="mock | anthropic | ollama")
    p.add_argument("--prompt", dest="prompt_variant", default=None,
                   help="zero_shot | cot | few_shot")
    p.add_argument("--limit", type=int, default=None, help="only run the first N problems")
    p.add_argument("--config", default=None, help="path to a config.yaml")
    a = p.parse_args(argv)
    run(a.dataset, a.provider, a.prompt_variant, a.limit, a.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
