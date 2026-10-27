"""Prompt variants for code generation. Each takes the problem `prompt` (a function
signature + docstring) and returns the string sent to the model.

The point of several variants is the comparison grid in report.py: "zero-shot vs
chain-of-thought vs few-shot, across 2 models". Add one here, reference it by name
in config.yaml or --prompt, and it appears in the grid."""
from __future__ import annotations

import re
from typing import Callable

_INSTRUCTION = (
    "You are an expert Python programmer. Complete the function below so it satisfies "
    "its docstring. Return ONLY the complete function definition as runnable Python — "
    "no explanation, no example usage, no markdown fences."
)


def zero_shot(prompt: str) -> str:
    return f"{_INSTRUCTION}\n\n{prompt}"


def cot(prompt: str) -> str:
    """Let the model reason, but still end with a clean code block that
    extract_code() can recover."""
    return (
        f"{_INSTRUCTION}\n\n{prompt}\n\n"
        "First think briefly about edge cases, then give the final implementation as "
        "a single ```python code block containing the complete function."
    )


_FEWSHOT = '''\
Example
Complete:
def add(a, b):
    """Return the sum of a and b."""
Answer:
def add(a, b):
    """Return the sum of a and b."""
    return a + b
'''


def few_shot(prompt: str) -> str:
    return (
        f"{_INSTRUCTION}\n\nHere is the format:\n\n{_FEWSHOT}\n"
        f"Now complete this one.\nComplete:\n{prompt}\nAnswer:\n"
    )


VARIANTS: dict[str, Callable[[str], str]] = {
    "zero_shot": zero_shot,
    "cot": cot,
    "few_shot": few_shot,
}


def build_prompt(variant: str, prompt: str) -> str:
    try:
        return VARIANTS[variant](prompt)
    except KeyError:
        raise ValueError(f"Unknown prompt variant {variant!r}. Have: {list(VARIANTS)}")


def extract_code(text: str, prompt: str, entry_point: str) -> str:
    """Recover runnable Python from a model response.

    Models answer code-completion prompts in three common shapes, and the harness
    must handle all of them or it penalizes formatting, not correctness:
      1. a ```python fenced block (chain-of-thought / chatty models)
      2. a full `def entry_point(...): ...` definition (most instruct models)
      3. only the function *body* (continuation-style; needs the signature prepended)
    """
    # 1. Prefer a fenced block.
    m = re.search(r"```(?:python|py)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    body = m.group(1) if m else text

    # 2. If it already contains the full def, take from there to the end.
    def_match = re.search(rf"(^|\n)\s*def\s+{re.escape(entry_point)}\b", body)
    if def_match:
        return body[def_match.start():].strip("\n")

    # 3. Otherwise assume it's a bare body (indented lines) and graft the signature
    #    from the original prompt onto it.
    stripped = body.strip("\n")
    # Prompt is "def f(...):\n    \"\"\"...\"\"\"\n"; keep it and append the body.
    if not stripped:
        return prompt  # empty -> let it fail honestly in the sandbox
    # If the model's body isn't indented, indent it so it's inside the function.
    lines = stripped.splitlines()
    if lines and not lines[0].startswith((" ", "\t")):
        lines = ["    " + ln if ln.strip() else ln for ln in lines]
    return prompt.rstrip("\n") + "\n" + "\n".join(lines)
