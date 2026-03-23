from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


def resolve_execution_fills(
    weights_df: pd.DataFrame,
    market_df: pd.DataFrame,
    execution_cfg: Dict[str, Any],
) -> pd.DataFrame:
    if weights_df.empty:
        return pd.DataFrame()

    delay_bars = int(execution_cfg.get("delay_bars", 1))
    holding_period_bars = int(execution_cfg.get("holding_period_bars", 1))
    entry_price_field = execution_cfg.get("entry_price", "open")
    exit_price_field = execution_cfg.get("exit_price", "close")

    schedule = pd.Index(sorted(market_df["timestamp"].drop_duplicates().tolist()))
    if schedule.empty:
        raise ValueError("Market data contains no timestamps.")

    fills = weights_df.copy()
    signal_bar_index = schedule.searchsorted(fills["signal_timestamp"])
    fills["signal_bar_index"] = signal_bar_index
    fills = fills[fills["signal_bar_index"] < len(schedule)].copy()
    if fills.empty:
        return fills

    fills["entry_bar_index"] = fills["signal_bar_index"] + delay_bars
    fills["exit_bar_index"] = fills["entry_bar_index"] + max(holding_period_bars, 1) - 1
    fills = fills[fills["exit_bar_index"] < len(schedule)].copy()
    if fills.empty:
        return fills

    fills["entry_timestamp"] = schedule.take(fills["entry_bar_index"].to_numpy())
    fills["exit_timestamp"] = schedule.take(fills["exit_bar_index"].to_numpy())
    fills["holding_period_bars"] = holding_period_bars

    entry_columns = ["timestamp", "asset", entry_price_field, "spread_bps", "adv", "volume", "volatility_20d"]
    exit_columns = ["timestamp", "asset", exit_price_field, "spread_bps"]

    entry_market = market_df[entry_columns].rename(
        columns={
            "timestamp": "entry_timestamp",
            entry_price_field: "entry_price",
            "spread_bps": "entry_spread_bps",
            "adv": "entry_adv",
            "volume": "entry_volume",
            "volatility_20d": "entry_volatility_20d",
        }
    )
    exit_market = market_df[exit_columns].rename(
        columns={
            "timestamp": "exit_timestamp",
            exit_price_field: "exit_price",
            "spread_bps": "exit_spread_bps",
        }
    )

    fills = fills.merge(entry_market, on=["entry_timestamp", "asset"], how="left")
    fills = fills.merge(exit_market, on=["exit_timestamp", "asset"], how="left")
    fills = fills.dropna(subset=["entry_price", "exit_price"]).copy()
    if fills.empty:
        return fills

    fills["entry_price"] = pd.to_numeric(fills["entry_price"], errors="coerce")
    fills["exit_price"] = pd.to_numeric(fills["exit_price"], errors="coerce")
    fills = fills.dropna(subset=["entry_price", "exit_price"]).copy()
    if fills.empty:
        return fills

    fills["realized_return"] = fills["exit_price"] / fills["entry_price"] - 1.0
    fills["gross_pnl"] = fills["target_weight"] * fills["realized_return"]
    fills["turnover"] = 2.0 * fills["target_weight"].abs()
    fills["entry_adv"] = fills["entry_adv"].fillna(fills["entry_volume"]).fillna(1.0).replace(0.0, 1.0)
    fills["entry_volatility_20d"] = fills["entry_volatility_20d"].fillna(0.0)
    fills["entry_spread_bps"] = fills["entry_spread_bps"].fillna(0.0)
    fills["exit_spread_bps"] = fills["exit_spread_bps"].fillna(0.0)
    fills["bar_gap"] = fills["entry_bar_index"] - fills["signal_bar_index"]

    return fills.sort_values(["entry_timestamp", "asset"]).reset_index(drop=True)
