from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

import pandas as pd


def build_robustness_scenarios(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    baseline_cfg = config.get("baseline", {})
    execution_cfg = baseline_cfg.get("execution", {})
    costs_cfg = baseline_cfg.get("costs", {})
    robustness_cfg = baseline_cfg.get("robustness", {})
    smaller_universe_cfg = robustness_cfg.get("smaller_universe", {})

    base_delay = int(execution_cfg.get("delay_bars", 1))
    base_commission = float(costs_cfg.get("commission_bps", 0.0))
    base_slippage = float(costs_cfg.get("slippage_bps", 0.0))
    asset_limit_ratio = float(smaller_universe_cfg.get("asset_limit_ratio", 0.75))

    scenarios: List[Dict[str, Any]] = []

    def _add(
        name: str,
        group: str,
        dimension: str,
        value: Any,
        description: str,
        updater,
    ) -> None:
        scenario_config = deepcopy(config)
        updater(scenario_config)
        scenarios.append(
            {
                "name": name,
                "group": group,
                "dimension": dimension,
                "value": value,
                "description": description,
                "config": scenario_config,
            }
        )

    _add(
        name="base_case",
        group="base",
        dimension="base_case",
        value="base",
        description="Unchanged base configuration.",
        updater=lambda cfg: None,
    )
    _add(
        name="delay_plus_1",
        group="delay",
        dimension="delay_bars",
        value=base_delay + 1,
        description=f"Execution delay increased from {base_delay} to {base_delay + 1}.",
        updater=lambda cfg: cfg["baseline"]["execution"].update({"delay_bars": base_delay + 1}),
    )
    _add(
        name="delay_plus_2",
        group="delay",
        dimension="delay_bars",
        value=base_delay + 2,
        description=f"Execution delay increased from {base_delay} to {base_delay + 2}.",
        updater=lambda cfg: cfg["baseline"]["execution"].update({"delay_bars": base_delay + 2}),
    )
    _add(
        name="fees_x2",
        group="cost",
        dimension="commission_bps",
        value=base_commission * 2.0,
        description=f"Commission fees doubled from {base_commission:g} bps to {base_commission * 2.0:g} bps.",
        updater=lambda cfg: cfg["baseline"]["costs"].update({"commission_bps": base_commission * 2.0}),
    )
    _add(
        name="slippage_x2",
        group="cost",
        dimension="slippage_bps",
        value=base_slippage * 2.0,
        description=f"Slippage doubled from {base_slippage:g} bps to {base_slippage * 2.0:g} bps.",
        updater=lambda cfg: cfg["baseline"]["costs"].update({"slippage_bps": base_slippage * 2.0}),
    )
    _add(
        name="smaller_universe",
        group="universe",
        dimension="asset_limit_ratio",
        value=asset_limit_ratio,
        description=f"Keep only the top {asset_limit_ratio:.0%} of assets by signal coverage.",
        updater=lambda cfg: cfg.setdefault("data", {}).update({"asset_limit_ratio": asset_limit_ratio}),
    )
    return scenarios


def finalize_robustness_comparison(robustness_df: pd.DataFrame) -> pd.DataFrame:
    if robustness_df.empty:
        return robustness_df

    out = robustness_df.copy()
    base_rows = out[out["scenario"] == "base_case"]
    if base_rows.empty:
        return out

    base_row = base_rows.iloc[0]
    for metric in ["net_total_return", "net_sharpe_ratio", "total_cost", "turnover_total"]:
        if metric in out.columns:
            out[f"delta_{metric}"] = out[metric] - base_row[metric]
    return out.sort_values(["group", "scenario"]).reset_index(drop=True)


def _format_delta(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:+.6f}"


def render_robustness_summary_markdown(config: Dict[str, Any], robustness_df: pd.DataFrame) -> str:
    lines = [
        "# Robustness Summary",
        "",
        "## Scenarios Tested",
    ]

    if robustness_df.empty:
        lines.extend(["- No robustness scenarios were generated.", ""])
        return "\n".join(lines) + "\n"

    for _, row in robustness_df.iterrows():
        status = row.get("status", "ok")
        description = row.get("description", "")
        lines.append(f"- `{row['scenario']}`: {description} Status: `{status}`.")

    ok_df = robustness_df[robustness_df.get("status", "ok") == "ok"].copy()
    if ok_df.empty or "base_case" not in ok_df["scenario"].values:
        lines.extend(["", "## Interpretation", "- No successful robustness comparison was produced."])
        return "\n".join(lines) + "\n"

    base_row = ok_df[ok_df["scenario"] == "base_case"].iloc[0]
    stressed = ok_df[ok_df["scenario"] != "base_case"].copy()
    if stressed.empty:
        lines.extend(["", "## Interpretation", "- Only the base case was available."])
        return "\n".join(lines) + "\n"

    worst_return = stressed.sort_values("delta_net_total_return").iloc[0]
    worst_sharpe = stressed.sort_values("delta_net_sharpe_ratio").iloc[0]
    group_worst = (
        stressed.groupby("group", dropna=False)["delta_net_total_return"]
        .min()
        .sort_values()
    )
    most_sensitive_group = group_worst.index[0]

    if most_sensitive_group == "delay":
        takeaway = "Performance is more sensitive to execution timing than to the direct cost shocks tested here."
    elif most_sensitive_group == "cost":
        takeaway = "Performance is more sensitive to trading-cost assumptions than to execution delay in this setup."
    else:
        takeaway = "Performance is meaningfully affected by signal breadth and tradable-universe reduction."

    lines.extend(
        [
            "",
            "## Most Harmful Assumptions",
            f"- Largest net return hit: `{worst_return['scenario']}` with delta `{_format_delta(worst_return.get('delta_net_total_return'))}` versus base.",
            f"- Largest net Sharpe hit: `{worst_sharpe['scenario']}` with delta `{_format_delta(worst_sharpe.get('delta_net_sharpe_ratio'))}` versus base.",
            "",
            "## Interpretation",
            f"- Base case net total return: `{base_row.get('net_total_return')}`.",
            f"- Base case net Sharpe ratio: `{base_row.get('net_sharpe_ratio')}`.",
            f"- {takeaway}",
        ]
    )
    return "\n".join(lines) + "\n"
