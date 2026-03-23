from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pandas as pd

from src.data.news_to_signal_adapter import load_news_to_signal_signal_frame
from src.utils.signal_schema import filter_standard_signal_frame, load_standard_signal_frame


def _load_signal_frame(
    path_value: str,
    file_format: str = "auto",
    signal_adapter: str = "auto",
) -> tuple[pd.DataFrame, Dict[str, Any]]:
    input_path = Path(path_value).expanduser()
    use_news_to_signal_adapter = signal_adapter == "news_to_signal" or input_path.is_dir() or input_path.name == "signals_manifest.json"
    if use_news_to_signal_adapter:
        return load_news_to_signal_signal_frame(input_path, file_format=file_format)

    resolved_format = file_format if file_format != "auto" else input_path.suffix.lower().lstrip(".")
    return (
        load_standard_signal_frame(input_path, file_format=file_format),
        {
            "signal_input_kind": "standard_signal_file",
            "signal_input_path": str(input_path),
            "resolved_signal_path": str(input_path),
            "resolved_signal_format": str(resolved_format),
            "signal_manifest_path": "",
            "upstream_run_dir": "",
        },
    )


def apply_signal_data_filters(signal_df: pd.DataFrame, data_cfg: Dict[str, Any]) -> pd.DataFrame:
    asset_limit = data_cfg.get("asset_limit")
    asset_limit_ratio = data_cfg.get("asset_limit_ratio")
    if asset_limit in {None, ""} and asset_limit_ratio in {None, ""}:
        return signal_df

    asset_counts = (
        signal_df.groupby("asset")
        .size()
        .reset_index(name="n_obs")
        .sort_values(["n_obs", "asset"], ascending=[False, True])
        .reset_index(drop=True)
    )
    if asset_counts.empty:
        return signal_df

    n_assets = len(asset_counts)
    if asset_limit not in {None, ""}:
        n_keep = max(1, min(n_assets, int(asset_limit)))
    else:
        ratio = float(asset_limit_ratio)
        if ratio <= 0:
            return signal_df
        if ratio < 1:
            n_keep = max(1, min(n_assets, int(n_assets * ratio)))
        else:
            n_keep = max(1, min(n_assets, int(ratio)))

    allowed_assets = set(asset_counts.head(n_keep)["asset"].tolist())
    return signal_df[signal_df["asset"].isin(allowed_assets)].reset_index(drop=True)


def load_signals_from_config(config: dict) -> tuple[pd.DataFrame, Dict[str, Any]]:
    data_cfg = config.get("data", {})
    features_cfg = config.get("features", {})

    signal_df, signal_metadata = _load_signal_frame(
        data_cfg["signal_path"],
        file_format=data_cfg.get("signal_format", "auto"),
        signal_adapter=data_cfg.get("signal_adapter", "auto"),
    )
    signal_df = filter_standard_signal_frame(
        signal_df,
        signal_name=features_cfg.get("signal_name"),
        signal_version=features_cfg.get("signal_version"),
        horizon=features_cfg.get("horizon"),
        source=features_cfg.get("source"),
        start=data_cfg.get("start"),
        end=data_cfg.get("end"),
    )
    signal_df = apply_signal_data_filters(signal_df, data_cfg)
    if signal_df.empty:
        raise ValueError("No signals remain after applying the configured filters.")
    return signal_df, signal_metadata


def build_signal_coverage_table(signal_df: pd.DataFrame) -> pd.DataFrame:
    coverage = (
        signal_df.groupby("timestamp")
        .agg(
            n_assets=("asset", "nunique"),
            signal_mean=("signal_value", "mean"),
            signal_std=("signal_value", "std"),
        )
        .reset_index()
        .rename(columns={"timestamp": "signal_timestamp"})
    )
    coverage["signal_std"] = coverage["signal_std"].fillna(0.0)
    return coverage
