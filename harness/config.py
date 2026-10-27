"""Load config.yaml and .env. One place that reads configuration, so nothing
downstream has to know where settings live."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional at import time; only needed for real providers
    def load_dotenv(*_a, **_k):  # type: ignore
        return False

# Repo root = parent of the `harness/` package dir. All paths in config.yaml are
# resolved relative to this, so the harness runs the same from any CWD.
ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Read config.yaml (from the repo root unless `path` is given) and load .env."""
    load_dotenv(ROOT / ".env")
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = ROOT
    return cfg


def resolve(cfg: dict[str, Any], rel: str) -> Path:
    """Resolve a config-relative path to an absolute Path under the repo root."""
    return (cfg["_root"] / rel).resolve()
