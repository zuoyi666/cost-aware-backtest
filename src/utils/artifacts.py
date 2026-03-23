from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def to_serializable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): to_serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_serializable(item) for item in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def write_yaml_file(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(to_serializable(payload), handle, sort_keys=False)
    return path


def write_json_file(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_serializable(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def write_markdown_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_table(df: pd.DataFrame, path_without_suffix: Path) -> Path:
    path_without_suffix.parent.mkdir(parents=True, exist_ok=True)
    parquet_path = path_without_suffix.with_suffix(".parquet")
    csv_path = path_without_suffix.with_suffix(".csv")
    try:
        df.to_parquet(parquet_path, index=False)
        csv_path.unlink(missing_ok=True)
        return parquet_path
    except Exception:
        df.to_csv(csv_path, index=False)
        parquet_path.unlink(missing_ok=True)
        return csv_path
