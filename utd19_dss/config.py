"""Đọc cấu hình DSS (config/dss.yaml)."""
from __future__ import annotations

from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = BASE_DIR / "config" / "dss.yaml"


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG
    cfg = yaml.safe_load(p.read_text(encoding="utf-8"))
    cfg["_base"] = BASE_DIR
    return cfg


def resolve(cfg: dict, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (cfg["_base"] / p)


def artifacts_dir(cfg: dict) -> Path:
    d = resolve(cfg, cfg["artifacts_dir"])
    d.mkdir(parents=True, exist_ok=True)
    return d
