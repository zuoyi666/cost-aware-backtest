from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


def apply_transaction_costs(
    fills_df: pd.DataFrame,
    cost_cfg: Dict[str, Any],
) -> pd.DataFrame:
    if fills_df.empty:
        return fills_df

    commission_bps = float(cost_cfg.get("commission_bps", 0.0))
    slippage_bps = float(cost_cfg.get("slippage_bps", 0.0))
    fallback_half_spread_bps = float(cost_cfg.get("half_spread_bps", 0.0))
    impact_coefficient = float(cost_cfg.get("impact_coefficient", 0.0))
    cost_multiplier = float(cost_cfg.get("cost_multiplier", 1.0))

    fills = fills_df.copy()

    commission_cost = fills["target_weight"].abs() * (2.0 * commission_bps / 10000.0)
    slippage_cost = fills["target_weight"].abs() * (2.0 * slippage_bps / 10000.0)

    entry_half = fills["entry_spread_bps"].replace(0.0, np.nan) / 2.0
    exit_half = fills["exit_spread_bps"].replace(0.0, np.nan) / 2.0
    spread_cost_bps = entry_half.fillna(fallback_half_spread_bps) + exit_half.fillna(fallback_half_spread_bps)
    spread_cost = fills["target_weight"].abs() * (spread_cost_bps / 10000.0)

    if impact_coefficient > 0.0:
        impact_cost_bps = (
            impact_coefficient
            * fills["target_weight"].abs()
            * (1.0 + fills["entry_volatility_20d"].abs())
            / fills["entry_adv"].clip(lower=1.0)
            * 1_000_000.0
        )
    else:
        impact_cost_bps = 0.0
    impact_cost = fills["target_weight"].abs() * (impact_cost_bps / 10000.0)

    fills["commission_cost"] = commission_cost * cost_multiplier
    fills["slippage_cost"] = slippage_cost * cost_multiplier
    fills["spread_cost"] = spread_cost * cost_multiplier
    fills["impact_cost"] = impact_cost * cost_multiplier
    fills["total_cost"] = (
        fills["commission_cost"]
        + fills["slippage_cost"]
        + fills["spread_cost"]
        + fills["impact_cost"]
    )
    fills["net_pnl"] = fills["gross_pnl"] - fills["total_cost"]
    return fills
