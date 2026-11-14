from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd

COST_COMPONENTS = ("commission_cost", "slippage_cost", "spread_cost", "impact_cost")


def apply_transaction_costs(
    fills_df: pd.DataFrame,
    cost_cfg: Dict[str, Any],
) -> pd.DataFrame:
    """Charge each fill's round-trip costs as fractions of capital.

    Every component is split into the part paid when the position is entered and the part paid
    when it is exited (`<component>_entry`, `<component>_exit`), so that the portfolio time
    series can book each cost on the bar it is paid.

    - commission and slippage: `bps` per side, on the absolute target weight;
    - spread: half the quoted spread at entry plus half at exit (a missing or zero quote falls
      back to `half_spread_bps`);
    - impact (off by default): the square-root law, charged on each side,
      `impact_coefficient * daily_volatility * sqrt(traded_notional / adv_notional)`, where
      traded notional is `|weight| * book_notional` and ADV notional is the entry bar's ADV
      in shares times its entry price. A fill without ADV pays no impact.
    """
    if fills_df.empty:
        return fills_df

    commission_bps = float(cost_cfg.get("commission_bps", 0.0))
    slippage_bps = float(cost_cfg.get("slippage_bps", 0.0))
    fallback_half_spread_bps = float(cost_cfg.get("half_spread_bps", 0.0))
    impact_coefficient = float(cost_cfg.get("impact_coefficient", 0.0))
    book_notional = float(cost_cfg.get("book_notional", 1_000_000.0))
    cost_multiplier = float(cost_cfg.get("cost_multiplier", 1.0))

    fills = fills_df.copy()
    size = fills["target_weight"].abs()

    per_side = {
        "commission_cost": size * commission_bps / 10000.0,
        "slippage_cost": size * slippage_bps / 10000.0,
    }
    entry_half = fills["entry_spread_bps"].replace(0.0, np.nan).div(2.0).fillna(fallback_half_spread_bps)
    exit_half = fills["exit_spread_bps"].replace(0.0, np.nan).div(2.0).fillna(fallback_half_spread_bps)

    if impact_coefficient > 0.0:
        adv_notional = fills["entry_adv"] * fills["entry_price"]
        participation = (size * book_notional / adv_notional).where(adv_notional > 0)
        impact_side = (size * impact_coefficient * fills["entry_volatility_20d"].abs() * np.sqrt(participation)).fillna(0.0)
    else:
        impact_side = pd.Series(0.0, index=fills.index)

    sides = {
        "commission_cost": (per_side["commission_cost"], per_side["commission_cost"]),
        "slippage_cost": (per_side["slippage_cost"], per_side["slippage_cost"]),
        "spread_cost": (size * entry_half / 10000.0, size * exit_half / 10000.0),
        "impact_cost": (impact_side, impact_side),
    }
    for component, (entry_part, exit_part) in sides.items():
        fills[f"{component}_entry"] = entry_part * cost_multiplier
        fills[f"{component}_exit"] = exit_part * cost_multiplier
        fills[component] = fills[f"{component}_entry"] + fills[f"{component}_exit"]

    fills["total_cost"] = sum(fills[component] for component in COST_COMPONENTS)
    fills["net_pnl"] = fills["gross_pnl"] - fills["total_cost"]
    return fills
