"""Build the hand-written 'golden' problem set (10 problems you fully understand).

These are in HumanEval's exact shape (task_id / prompt / entry_point / test /
canonical_solution), so the harness code that runs them is identical to the code
that will run HumanEval. Get the full loop correct on these 10 before trusting a
big benchmark. Each reference solution is self-tested below, so a broken golden
problem can never silently fail every candidate.

    python -m harness.build_golden_set
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import load_config, resolve
from .sandbox import run_tests

# Each problem: (task_id, prompt, entry_point, canonical_solution, test, tags)
# `prompt` is the signature + docstring the model completes.
# `canonical_solution` is the function *body* (indented 4 spaces), appended to prompt.
# `test` defines check(candidate) and the harness calls check(entry_point).
PROBLEMS = [
    (
        "golden/add",
        'def add(a, b):\n    """Return the sum of two integers a and b."""\n',
        "add",
        "    return a + b\n",
        "def check(candidate):\n"
        "    assert candidate(2, 3) == 5\n"
        "    assert candidate(-1, 1) == 0\n"
        "    assert candidate(0, 0) == 0\n",
        ["math"],
    ),
    (
        "golden/is_palindrome",
        'def is_palindrome(s):\n'
        '    """Return True if the string s reads the same forwards and backwards,\n'
        '    ignoring case. Assume s contains only letters."""\n',
        "is_palindrome",
        "    s = s.lower()\n    return s == s[::-1]\n",
        "def check(candidate):\n"
        "    assert candidate('racecar') is True\n"
        "    assert candidate('Level') is True\n"
        "    assert candidate('hello') is False\n"
        "    assert candidate('') is True\n",
        ["string"],
    ),
    (
        "golden/factorial",
        'def factorial(n):\n'
        '    """Return n! for a non-negative integer n. factorial(0) == 1."""\n',
        "factorial",
        "    result = 1\n    for i in range(2, n + 1):\n        result *= i\n    return result\n",
        "def check(candidate):\n"
        "    assert candidate(0) == 1\n"
        "    assert candidate(1) == 1\n"
        "    assert candidate(5) == 120\n"
        "    assert candidate(10) == 3628800\n",
        ["math", "edge_case"],
    ),
    (
        "golden/fizzbuzz",
        'def fizzbuzz(n):\n'
        '    """Return a list of strings for 1..n: "Fizz" if divisible by 3,\n'
        '    "Buzz" if by 5, "FizzBuzz" if by both, else the number as a string."""\n',
        "fizzbuzz",
        "    out = []\n"
        "    for i in range(1, n + 1):\n"
        "        if i % 15 == 0:\n            out.append('FizzBuzz')\n"
        "        elif i % 3 == 0:\n            out.append('Fizz')\n"
        "        elif i % 5 == 0:\n            out.append('Buzz')\n"
        "        else:\n            out.append(str(i))\n"
        "    return out\n",
        "def check(candidate):\n"
        "    assert candidate(5) == ['1', '2', 'Fizz', '4', 'Buzz']\n"
        "    assert candidate(15)[-1] == 'FizzBuzz'\n"
        "    assert candidate(3) == ['1', '2', 'Fizz']\n",
        ["control_flow"],
    ),
    (
        "golden/two_sum",
        'def two_sum(nums, target):\n'
        '    """Given a list of integers nums and an integer target, return a pair of\n'
        '    indices [i, j] with i < j such that nums[i] + nums[j] == target. Assume\n'
        '    exactly one solution exists."""\n',
        "two_sum",
        "    seen = {}\n"
        "    for i, x in enumerate(nums):\n"
        "        if target - x in seen:\n            return [seen[target - x], i]\n"
        "        seen[x] = i\n",
        "def check(candidate):\n"
        "    assert candidate([2, 7, 11, 15], 9) == [0, 1]\n"
        "    assert candidate([3, 2, 4], 6) == [1, 2]\n"
        "    assert candidate([3, 3], 6) == [0, 1]\n",
        ["array", "hashmap"],
    ),
    (
        "golden/count_vowels",
        'def count_vowels(s):\n'
        '    """Return the number of vowels (a, e, i, o, u, case-insensitive) in s."""\n',
        "count_vowels",
        "    return sum(1 for c in s.lower() if c in 'aeiou')\n",
        "def check(candidate):\n"
        "    assert candidate('hello') == 2\n"
        "    assert candidate('XYZ') == 0\n"
        "    assert candidate('AEIOU') == 5\n"
        "    assert candidate('') == 0\n",
        ["string"],
    ),
    (
        "golden/flatten",
        'def flatten(nested):\n'
        '    """Flatten a list of lists into a single list, preserving order.\n'
        '    e.g. flatten([[1, 2], [3], []]) == [1, 2, 3]."""\n',
        "flatten",
        "    out = []\n    for sub in nested:\n        out.extend(sub)\n    return out\n",
        "def check(candidate):\n"
        "    assert candidate([[1, 2], [3], []]) == [1, 2, 3]\n"
        "    assert candidate([]) == []\n"
        "    assert candidate([[1], [2], [3]]) == [1, 2, 3]\n",
        ["list"],
    ),
    (
        "golden/gcd",
        'def gcd(a, b):\n'
        '    """Return the greatest common divisor of two positive integers."""\n',
        "gcd",
        "    while b:\n        a, b = b, a % b\n    return a\n",
        "def check(candidate):\n"
        "    assert candidate(12, 8) == 4\n"
        "    assert candidate(17, 5) == 1\n"
        "    assert candidate(100, 10) == 10\n",
        ["math"],
    ),
    (
        "golden/unique_sorted",
        'def unique_sorted(items):\n'
        '    """Return the unique elements of items, sorted in ascending order."""\n',
        "unique_sorted",
        "    return sorted(set(items))\n",
        "def check(candidate):\n"
        "    assert candidate([3, 1, 2, 3, 1]) == [1, 2, 3]\n"
        "    assert candidate([]) == []\n"
        "    assert candidate([5, 5, 5]) == [5]\n",
        ["list"],
    ),
    (
        "golden/title_case",
        'def title_case(s):\n'
        '    """Return s with the first letter of each word capitalized and the rest\n'
        '    lowercased. Words are separated by single spaces."""\n',
        "title_case",
        "    return ' '.join(w[:1].upper() + w[1:].lower() for w in s.split(' '))\n",
        "def check(candidate):\n"
        "    assert candidate('hello world') == 'Hello World'\n"
        "    assert candidate('PYTHON is FUN') == 'Python Is Fun'\n"
        "    assert candidate('a') == 'A'\n",
        ["string"],
    ),
]


def write_problems(dataset_dir: Path) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    with open(dataset_dir / "problems.jsonl", "w", encoding="utf-8") as f:
        for task_id, prompt, entry, sol, test, tags in PROBLEMS:
            f.write(json.dumps({
                "task_id": task_id,
                "prompt": prompt,
                "entry_point": entry,
                "test": test,
                "tags": tags,
                "canonical_solution": sol,
            }) + "\n")


def _selftest() -> None:
    """Every reference solution must pass its own tests in the sandbox. A broken
    golden problem would silently fail every candidate, so we assert it here."""
    for task_id, prompt, entry, sol, test, _ in PROBLEMS:
        code = prompt.rstrip("\n") + "\n" + sol
        outcome = run_tests(code, test, entry, timeout_s=10)
        if not outcome.passed:
            raise AssertionError(
                f"Reference solution for {task_id} failed its own tests "
                f"({outcome.status}): {outcome.detail}\n{outcome.stderr}"
            )
    print(f"  self-test: all {len(PROBLEMS)} reference solutions pass their own tests.")


def main() -> int:
    cfg = load_config()
    dataset_dir = resolve(cfg, cfg["datasets"]["golden"]["dir"])
    write_problems(dataset_dir)
    _selftest()
    print(f"Wrote {len(PROBLEMS)} problems: {dataset_dir / 'problems.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
