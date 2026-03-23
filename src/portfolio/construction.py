from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def construct_target_weights(
    signal_df: pd.DataFrame,
    portfolio_cfg: Dict[str, Any],
    holding_period_bars: int,
) -> pd.DataFrame:
    method = portfolio_cfg.get("method", "rank_long_short")
    if method != "rank_long_short":
        raise ValueError(f"Unsupported portfolio construction method: {method}")

    top_n = int(portfolio_cfg.get("top_n", 5))
    min_assets = int(portfolio_cfg.get("min_assets", max(2 * top_n, 4)))
    gross_leverage = float(portfolio_cfg.get("gross_leverage", 1.0))
    cohort_gross = gross_leverage / max(int(holding_period_bars), 1)

    rows: List[pd.DataFrame] = []
    for timestamp, group in signal_df.groupby("timestamp"):
        cohort = group.sort_values("signal_value").reset_index(drop=True)
        if len(cohort) < min_assets:
            continue

        n_select = min(top_n, len(cohort) // 2)
        if n_select < 1:
            continue

        shorts = cohort.head(n_select).copy()
        longs = cohort.tail(n_select).copy()

        shorts["leg"] = "short"
        longs["leg"] = "long"
        shorts["target_weight"] = -cohort_gross / 2.0 / len(shorts)
        longs["target_weight"] = cohort_gross / 2.0 / len(longs)

        rows.extend([shorts, longs])

    if not rows:
        return pd.DataFrame(
            columns=[
                "signal_timestamp",
                "asset",
                "signal_value",
                "signal_name",
                "signal_version",
                "horizon",
                "source",
                "leg",
                "target_weight",
            ]
        )

    weights = pd.concat(rows, ignore_index=True)
    weights = weights.rename(columns={"timestamp": "signal_timestamp"})
    return weights[
        [
            "signal_timestamp",
            "asset",
            "signal_value",
            "signal_name",
            "signal_version",
            "horizon",
            "source",
            "leg",
            "target_weight",
        ]
    ].sort_values(["signal_timestamp", "asset"]).reset_index(drop=True)
