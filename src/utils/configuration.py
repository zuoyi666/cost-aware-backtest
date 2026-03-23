from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_config(path: str) -> Dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_config_bundle(config_dir: str) -> Dict[str, Any]:
    config: Dict[str, Any] = {}
    for filename in ("data.yaml", "features.yaml", "baseline.yaml", "experiment.yaml"):
        path = Path(config_dir) / filename
        if not path.exists():
            continue
        config = _deep_merge(config, load_yaml_config(str(path)))
    return config


def load_pipeline_config(
    config_dir: str = "configs",
    overrides: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    config = _load_config_bundle(config_dir)
    config = _deep_merge(config, overrides or {})

    project_root = Path.cwd()
    config.setdefault("project_root", str(project_root))
    config.setdefault("environment", {})
    config["environment"]["pwd"] = str(project_root)

    run_synthetic = os.getenv("COST_AWARE_BACKTEST_SYNTHETIC")
    if run_synthetic is not None:
        config.setdefault("experiment", {})["synthetic"] = run_synthetic.lower() in {"1", "true", "yes"}

    return config
