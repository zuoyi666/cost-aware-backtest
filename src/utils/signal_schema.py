from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable

import pandas as pd

REQUIRED_SIGNAL_COLUMNS = [
    "timestamp",
    "asset",
    "signal_value",
    "signal_name",
    "signal_version",
    "horizon",
    "source",
]


def _read_tabular(path: str | Path, file_format: str = "auto") -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Data file not found: {file_path}")

    inferred_format = file_format
    if inferred_format == "auto":
        inferred_format = file_path.suffix.lower().lstrip(".")

    if inferred_format == "parquet":
        return pd.read_parquet(file_path)
    if inferred_format in {"csv", "txt"}:
        return pd.read_csv(file_path)
    raise ValueError(f"Unsupported tabular format: {file_format}")


def validate_standard_signal_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_SIGNAL_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required signal columns: {missing}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce", utc=False).dt.tz_localize(None)
    out["asset"] = out["asset"].astype("string").str.strip()
    out["signal_name"] = out["signal_name"].astype("string").str.strip()
    out["signal_version"] = out["signal_version"].astype("string").str.strip()
    out["horizon"] = out["horizon"].astype("string").str.strip()
    out["source"] = out["source"].astype("string").str.strip()
    out["signal_value"] = pd.to_numeric(out["signal_value"], errors="coerce")

    invalid_mask = out[REQUIRED_SIGNAL_COLUMNS].isnull().any(axis=1)
    if invalid_mask.any():
        raise ValueError(
            "Signal export contains null or invalid values in required columns."
        )

    duplicate_keys = ["timestamp", "asset", "signal_name", "signal_version", "horizon", "source"]
    if out.duplicated(duplicate_keys).any():
        raise ValueError("Signal export contains duplicate downstream signal keys.")

    return out.sort_values(["timestamp", "asset", "signal_name"]).reset_index(drop=True)[REQUIRED_SIGNAL_COLUMNS]


def load_standard_signal_frame(path: str | Path, file_format: str = "auto") -> pd.DataFrame:
    return validate_standard_signal_schema(_read_tabular(path, file_format=file_format))


def filter_standard_signal_frame(
    df: pd.DataFrame,
    signal_name: str | None = None,
    signal_version: str | None = None,
    horizon: str | int | None = None,
    source: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if signal_name:
        out = out[out["signal_name"] == signal_name]
    if signal_version:
        out = out[out["signal_version"] == signal_version]
    if horizon is not None and horizon != "":
        out = out[out["horizon"] == str(horizon)]
    if source:
        out = out[out["source"] == source]
    if start:
        out = out[out["timestamp"] >= pd.Timestamp(start)]
    if end:
        out = out[out["timestamp"] <= pd.Timestamp(end)]
    return out.sort_values(["timestamp", "asset"]).reset_index(drop=True)


def to_standard_signal_long_format(
    df: pd.DataFrame,
    signal_cols: Iterable[str],
    signal_version: str = "v1",
    horizon: str | int = "1",
    source: str = "unknown",
) -> pd.DataFrame:
    cols = list(signal_cols)
    base = df.copy()
    if "date" not in base.columns or "ticker" not in base.columns:
        raise ValueError("Wide signal conversion expects `date` and `ticker` columns.")
    base["date"] = pd.to_datetime(base["date"]).dt.tz_localize(None)

    long_df = (
        base.melt(
            id_vars=["date", "ticker"],
            value_vars=cols,
            var_name="signal_name",
            value_name="signal_value",
        )
        .rename(columns={"date": "timestamp", "ticker": "asset"})
    )
    long_df["signal_version"] = signal_version
    long_df["horizon"] = str(horizon)
    long_df["source"] = source
    return validate_standard_signal_schema(long_df)


def write_signal_snapshot(
    df: pd.DataFrame,
    output_dir: Path,
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    signal_df = validate_standard_signal_schema(df)

    parquet_path = output_dir / "signals.parquet"
    csv_path = output_dir / "signals.csv"
    try:
        signal_df.to_parquet(parquet_path, index=False)
        used_path = parquet_path
        used_format = "parquet"
        csv_path.unlink(missing_ok=True)
    except Exception:
        signal_df.to_csv(csv_path, index=False)
        used_path = csv_path
        used_format = "csv"
        parquet_path.unlink(missing_ok=True)

    manifest = {
        "schema": {
            "required_columns": REQUIRED_SIGNAL_COLUMNS,
            "signal_names": sorted(signal_df["signal_name"].unique().tolist()),
            "signal_versions": sorted(signal_df["signal_version"].unique().tolist()),
            "horizons": sorted(signal_df["horizon"].unique().tolist()),
            "sources": sorted(signal_df["source"].unique().tolist()),
        },
        "file": {
            "format": used_format,
            "path": str(used_path),
        },
        "record_count": int(len(signal_df)),
    }

    manifest_path = output_dir / "signals_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"signal_file": str(used_path), "manifest": str(manifest_path)}
