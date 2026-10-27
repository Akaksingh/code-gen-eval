"""Provider interface. Every backend returns the same `Generation` so the core
loop never knows (or cares) which model produced the SQL. This is the seam that
lets Project 3 swap in a distilled model later, and the one that makes the
Project 1 model-comparison grid a one-line config change.

Providers:
  mock       — no network, no key. Returns gold SQL for `correct_fraction` of calls
               and a plausible-but-wrong query otherwise. Used to prove the harness
               itself is correct before you trust a real model.
  anthropic  — wraps the Anthropic SDK (Claude). Needs ANTHROPIC_API_KEY.
  ollama     — wraps a local Ollama server over HTTP. Free, no key.
"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

# Approximate USD per 1M tokens, used to turn token counts into a cost number.
# These are the knob that produces the "$/100 queries" metric; update when prices
# change. Local/mock models are free.
PRICING = {
    # model substring : (input $/1M, output $/1M)
    "claude-haiku-5-5": (0.80, 4.00),
    "claude-sonnet-5-5": (3.00, 15.00),
    "claude-opus-5-5": (15.00, 75.00),
}


@dataclass
class Generation:
    """Everything the harness logs about one LLM call."""
    text: str                       # the raw model output (SQL, possibly fenced)
    input_tokens: int = 0
    output_tokens: int = 0
    latency_s: float = 0.0
    cost_usd: float = 0.0
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)  # provider-specific extras


def _price(model: str, input_tokens: int, output_tokens: int) -> float:
    for key, (pin, pout) in PRICING.items():
        if key in model:
            return input_tokens / 1e6 * pin + output_tokens / 1e6 * pout
    return 0.0  # unknown / local / mock model => free


class LLMClient(Protocol):
    """The whole contract. A prompt in, a Generation out."""
    model: str

    def generate(self, prompt: str) -> Generation: ...


# ----------------------------------------------------------------------------- #
# Mock
# ----------------------------------------------------------------------------- #
class MockClient:
    """Deterministic fake. Doesn't call anything.

    To make the loop runnable with no key, the mock needs the problem's reference
    solution so it can return a correct completion for a fraction of problems. The
    core loop passes it via a side channel (`set_reference`) right before calling
    generate — real providers have no such method and never see the reference.
    """

    def __init__(self, cfg: dict[str, Any]):
        self.model = cfg.get("model", "mock-v1")
        self.correct_fraction = float(cfg.get("correct_fraction", 0.7))
        self._seed = int(cfg.get("seed", 7))
        self._prompt = ""        # the function signature+docstring to complete
        self._reference = ""     # the canonical solution body (indented)

    def set_reference(self, problem_prompt: str, canonical_solution: str) -> None:
        self._prompt = problem_prompt
        self._reference = canonical_solution

    def generate(self, prompt: str) -> Generation:
        # Deterministic per-prompt coin flip so runs are reproducible.
        h = hashlib.sha256(f"{self._seed}:{prompt}".encode()).hexdigest()
        roll = int(h[:8], 16) / 0xFFFFFFFF
        if roll < self.correct_fraction and self._reference:
            # A correct completion: the signature+docstring plus the reference body.
            text = self._prompt.rstrip("\n") + "\n" + self._reference
        else:
            # A plausible-but-buggy completion that exercises the harness's failure
            # paths: the reference body with one mutation (wrong answer), or a body
            # that raises, or one with a syntax error.
            rng = random.Random(h)
            kind = rng.choice(["off_by_one", "raises", "syntax", "wrong_return"])
            body = self._reference or "    pass"
            if kind == "off_by_one" and "return" in body:
                text = self._prompt.rstrip("\n") + "\n" + body.replace("return ", "return 1 + ", 1)
            elif kind == "raises":
                text = self._prompt.rstrip("\n") + "\n    raise ValueError('boom')"
            elif kind == "syntax":
                text = self._prompt.rstrip("\n") + "\n    return (  # unclosed paren"
            else:  # wrong_return
                text = self._prompt.rstrip("\n") + "\n    return None"
        in_tok, out_tok = len(prompt) // 4, max(1, len(text) // 4)
        return Generation(text=text, input_tokens=in_tok, output_tokens=out_tok,
                          latency_s=0.0, cost_usd=0.0, model=self.model)


# ----------------------------------------------------------------------------- #
# Anthropic (Claude)
# ----------------------------------------------------------------------------- #
class AnthropicClient:
    def __init__(self, cfg: dict[str, Any]):
        from anthropic import Anthropic  # imported lazily so mock/ollama need no install
        self._client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = cfg["model"]
        self.temperature = float(cfg.get("temperature", 0.0))
        self.max_tokens = int(cfg.get("max_tokens", 1024))

    def generate(self, prompt: str) -> Generation:
        t0 = time.perf_counter()
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        latency = time.perf_counter() - t0
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        return Generation(
            text=text, input_tokens=in_tok, output_tokens=out_tok,
            latency_s=latency, cost_usd=_price(self.model, in_tok, out_tok),
            model=self.model, raw={"stop_reason": resp.stop_reason},
        )


# ----------------------------------------------------------------------------- #
# Ollama (local)
# ----------------------------------------------------------------------------- #
class OllamaClient:
    def __init__(self, cfg: dict[str, Any]):
        self.model = cfg["model"]
        self.host = cfg.get("host", "http://localhost:11434")
        self.temperature = float(cfg.get("temperature", 0.0))
        self.num_predict = int(cfg.get("num_predict", 1024))

    def generate(self, prompt: str) -> Generation:
        import requests  # lazy
        t0 = time.perf_counter()
        resp = requests.post(
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": self.temperature, "num_predict": self.num_predict},
            },
            timeout=120,
        )
        resp.raise_for_status()
        latency = time.perf_counter() - t0
        data = resp.json()
        return Generation(
            text=data.get("response", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            latency_s=latency, cost_usd=0.0,  # local = free
            model=self.model, raw={"done_reason": data.get("done_reason")},
        )


def get_client(cfg: dict[str, Any], provider: str | None = None) -> LLMClient:
    """Factory. `cfg` is the full loaded config; `provider` overrides cfg['provider']."""
    name = provider or cfg["provider"]
    pcfg = cfg["providers"][name]
    if name == "mock":
        return MockClient(pcfg)
    if name == "anthropic":
        return AnthropicClient(pcfg)
    if name == "ollama":
        return OllamaClient(pcfg)
    raise ValueError(f"Unknown provider: {name!r}. Expected mock | anthropic | ollama.")
