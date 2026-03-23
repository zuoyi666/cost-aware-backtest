from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd

from src.utils.signal_schema import load_standard_signal_frame


def _first_existing_path(paths: list[Path]) -> Path | None:
    seen: set[Path] = set()
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None


def _resolve_manifest_signal_path(manifest_path: Path, raw_path: str) -> Path:
    payload_path = Path(raw_path).expanduser()
    if payload_path.is_absolute() and payload_path.exists():
        return payload_path

    candidates = [
        manifest_path.parent / payload_path,
        manifest_path.parent / payload_path.name,
    ]
    candidates.extend(parent / payload_path for parent in manifest_path.parents)

    resolved = _first_existing_path(candidates)
    if resolved is None:
        raise FileNotFoundError(
            f"Unable to resolve signal file from manifest {manifest_path}: {raw_path}"
        )
    return resolved


def resolve_news_to_signal_input(path_value: str | Path, file_format: str = "auto") -> Dict[str, str]:
    input_path = Path(path_value).expanduser()
    if not input_path.exists():
        raise FileNotFoundError(f"news-to-signal input path not found: {input_path}")

    if input_path.is_dir():
        manifest_path = input_path / "signals_manifest.json"
        if manifest_path.exists():
            metadata = resolve_news_to_signal_input(manifest_path, file_format=file_format)
            metadata["signal_input_kind"] = "news_to_signal_run_dir"
            metadata["signal_input_path"] = str(input_path)
            metadata["upstream_run_dir"] = str(input_path)
            return metadata

        for filename in ("signals.parquet", "signals.csv"):
            candidate = input_path / filename
            if candidate.exists():
                return {
                    "signal_input_kind": "news_to_signal_run_dir",
                    "signal_input_path": str(input_path),
                    "resolved_signal_path": str(candidate),
                    "resolved_signal_format": candidate.suffix.lower().lstrip("."),
                    "signal_manifest_path": "",
                    "upstream_run_dir": str(input_path),
                }

        raise FileNotFoundError(f"No signal export found under news-to-signal run directory: {input_path}")

    if input_path.name == "signals_manifest.json":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        file_info = payload.get("file", {})
        raw_signal_path = file_info.get("path")
        if not raw_signal_path:
            raise ValueError(f"Manifest does not include `file.path`: {input_path}")

        resolved_signal_path = _resolve_manifest_signal_path(input_path, raw_signal_path)
        resolved_format = file_info.get("format") or file_format
        if resolved_format == "auto":
            resolved_format = resolved_signal_path.suffix.lower().lstrip(".")

        return {
            "signal_input_kind": "news_to_signal_manifest",
            "signal_input_path": str(input_path),
            "resolved_signal_path": str(resolved_signal_path),
            "resolved_signal_format": str(resolved_format),
            "signal_manifest_path": str(input_path),
            "upstream_run_dir": str(input_path.parent),
        }

    resolved_format = file_format if file_format != "auto" else input_path.suffix.lower().lstrip(".")
    return {
        "signal_input_kind": "news_to_signal_signal_file",
        "signal_input_path": str(input_path),
        "resolved_signal_path": str(input_path),
        "resolved_signal_format": str(resolved_format),
        "signal_manifest_path": "",
        "upstream_run_dir": str(input_path.parent),
    }


def load_news_to_signal_signal_frame(
    path_value: str | Path,
    file_format: str = "auto",
) -> tuple[pd.DataFrame, Dict[str, str]]:
    metadata = resolve_news_to_signal_input(path_value, file_format=file_format)
    signal_df = load_standard_signal_frame(
        metadata["resolved_signal_path"],
        file_format=metadata["resolved_signal_format"],
    )
    return signal_df, metadata
