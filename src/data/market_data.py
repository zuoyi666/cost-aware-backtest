from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.utils.signal_schema import _read_tabular

REQUIRED_MARKET_COLUMNS = ["timestamp", "asset", "open", "close"]


def validate_market_data_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_MARKET_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required market data columns: {missing}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=False).dt.tz_localize(None)
    out["asset"] = out["asset"].astype(str)
    out["open"] = pd.to_numeric(out["open"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["timestamp", "asset", "open", "close"])

    if "volume" in out.columns:
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    else:
        out["volume"] = 0.0

    if "adv" in out.columns:
        out["adv"] = pd.to_numeric(out["adv"], errors="coerce").fillna(out["volume"])
    else:
        out["adv"] = out["volume"].replace(0.0, 1.0)

    if "spread_bps" in out.columns:
        out["spread_bps"] = pd.to_numeric(out["spread_bps"], errors="coerce").fillna(0.0)
    else:
        out["spread_bps"] = 0.0

    if "volatility_20d" in out.columns:
        out["volatility_20d"] = pd.to_numeric(out["volatility_20d"], errors="coerce").fillna(0.0)
    else:
        close_returns = out.sort_values(["asset", "timestamp"]).groupby("asset")["close"].pct_change()
        out["volatility_20d"] = (
            close_returns.fillna(0.0)
            .groupby(out["asset"])
            .transform(lambda s: s.rolling(5, min_periods=1).std().fillna(0.0))
        )

    return out.sort_values(["timestamp", "asset"]).reset_index(drop=True)


def load_market_data_frame(path: str | Path, file_format: str = "auto") -> pd.DataFrame:
    return validate_market_data_schema(_read_tabular(path, file_format=file_format))


def filter_market_data_frame(
    df: pd.DataFrame,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    out = df.copy()
    if start:
        out = out[out["timestamp"] >= pd.Timestamp(start)]
    if end:
        out = out[out["timestamp"] <= pd.Timestamp(end)]
    return out.sort_values(["timestamp", "asset"]).reset_index(drop=True)
