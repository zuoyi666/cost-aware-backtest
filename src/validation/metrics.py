from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


def build_portfolio_timeseries(fills_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if fills_df.empty:
        empty = pd.DataFrame()
        return empty, empty

    portfolio_ts = (
        fills_df.groupby("exit_timestamp", as_index=False)
        .agg(
            gross_pnl=("gross_pnl", "sum"),
            net_pnl=("net_pnl", "sum"),
            total_cost=("total_cost", "sum"),
            commission_cost=("commission_cost", "sum"),
            slippage_cost=("slippage_cost", "sum"),
            spread_cost=("spread_cost", "sum"),
            impact_cost=("impact_cost", "sum"),
            n_positions=("asset", "count"),
        )
        .rename(columns={"exit_timestamp": "timestamp"})
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    turnover_ts = (
        fills_df.groupby("entry_timestamp", as_index=False)
        .agg(
            turnover=("turnover", "sum"),
            n_trades=("asset", "count"),
        )
        .rename(columns={"entry_timestamp": "timestamp"})
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    portfolio_ts["gross_wealth"] = (1.0 + portfolio_ts["gross_pnl"]).cumprod()
    portfolio_ts["net_wealth"] = (1.0 + portfolio_ts["net_pnl"]).cumprod()
    portfolio_ts["gross_cumulative_return"] = portfolio_ts["gross_wealth"] - 1.0
    portfolio_ts["net_cumulative_return"] = portfolio_ts["net_wealth"] - 1.0
    return portfolio_ts, turnover_ts


def _safe_float(value: float | int | np.floating | np.integer | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    if not np.isfinite(value):
        return None
    return value


def _compute_drawdown(wealth: pd.Series) -> float | None:
    if wealth.empty:
        return None
    running_max = wealth.cummax()
    drawdown = wealth / running_max - 1.0
    return _safe_float(drawdown.min())


def _compute_return_stats(returns: pd.Series, periods_per_year: float) -> Dict[str, Any]:
    if returns.empty:
        return {
            "n_periods": 0,
            "mean_return": None,
            "volatility": None,
            "annualized_return": None,
            "annualized_volatility": None,
            "sharpe_ratio": None,
            "hit_rate": None,
            "total_return": None,
            "max_drawdown": None,
        }

    clean_returns = returns.fillna(0.0)
    mean_return = clean_returns.mean()
    volatility = clean_returns.std(ddof=0)
    wealth = (1.0 + clean_returns).cumprod()

    sharpe = None
    if volatility > 0:
        sharpe = mean_return / volatility * np.sqrt(periods_per_year)

    return {
        "n_periods": int(clean_returns.shape[0]),
        "mean_return": _safe_float(mean_return),
        "volatility": _safe_float(volatility),
        "annualized_return": _safe_float(mean_return * periods_per_year),
        "annualized_volatility": _safe_float(volatility * np.sqrt(periods_per_year)),
        "sharpe_ratio": _safe_float(sharpe),
        "hit_rate": _safe_float((clean_returns > 0).mean()),
        "total_return": _safe_float(wealth.iloc[-1] - 1.0),
        "max_drawdown": _safe_float(_compute_drawdown(wealth)),
    }


def compute_metrics_payload(
    signal_df: pd.DataFrame,
    weights_df: pd.DataFrame,
    fills_df: pd.DataFrame,
    portfolio_ts: pd.DataFrame,
    turnover_ts: pd.DataFrame,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    metrics_cfg = config.get("baseline", {}).get("metrics", {})
    periods_per_year = float(
        metrics_cfg.get("periods_per_year")
        or metrics_cfg.get("bars_per_day", 1) * metrics_cfg.get("trading_days_per_year", 252)
    )

    gross_stats = _compute_return_stats(portfolio_ts["gross_pnl"], periods_per_year) if not portfolio_ts.empty else _compute_return_stats(pd.Series(dtype=float), periods_per_year)
    net_stats = _compute_return_stats(portfolio_ts["net_pnl"], periods_per_year) if not portfolio_ts.empty else _compute_return_stats(pd.Series(dtype=float), periods_per_year)

    total_gross = float(fills_df["gross_pnl"].sum()) if not fills_df.empty else 0.0
    total_cost = float(fills_df["total_cost"].sum()) if not fills_df.empty else 0.0

    cost_breakdown = {
        "commission_cost": _safe_float(fills_df["commission_cost"].sum() if not fills_df.empty else 0.0),
        "slippage_cost": _safe_float(fills_df["slippage_cost"].sum() if not fills_df.empty else 0.0),
        "spread_cost": _safe_float(fills_df["spread_cost"].sum() if not fills_df.empty else 0.0),
        "impact_cost": _safe_float(fills_df["impact_cost"].sum() if not fills_df.empty else 0.0),
        "total_cost": _safe_float(total_cost),
        "cost_as_pct_gross_pnl": _safe_float(total_cost / abs(total_gross)) if abs(total_gross) > 1e-12 else None,
    }

    portfolio_cfg = config.get("baseline", {}).get("portfolio", {})
    execution_cfg = config.get("baseline", {}).get("execution", {})
    executed_cohorts = fills_df["signal_timestamp"].nunique() if not fills_df.empty else 0
    diagnostics = {
        "input_signal_rows": int(len(signal_df)),
        "signal_assets": int(signal_df["asset"].nunique()) if not signal_df.empty else 0,
        "signal_timestamps": int(signal_df["timestamp"].nunique()) if not signal_df.empty else 0,
        "target_signal_rows": int(len(weights_df)),
        "target_cohorts": int(weights_df["signal_timestamp"].nunique()) if not weights_df.empty else 0,
        "tradable_signal_rows": int(len(fills_df)),
        "tradable_cohorts": int(executed_cohorts),
        "fills": int(len(fills_df)),
        "avg_positions_per_cohort": _safe_float(fills_df.groupby("signal_timestamp")["asset"].count().mean()) if not fills_df.empty else None,
        "turnover_total": _safe_float(turnover_ts["turnover"].sum() if not turnover_ts.empty else 0.0),
        "turnover_mean": _safe_float(turnover_ts["turnover"].mean() if not turnover_ts.empty else 0.0),
        "delay_bars": int(execution_cfg.get("delay_bars", 1)),
        "holding_period_bars": int(execution_cfg.get("holding_period_bars", 1)),
        "top_n": int(portfolio_cfg.get("top_n", 0)),
        "gross_leverage": _safe_float(portfolio_cfg.get("gross_leverage", 1.0)),
    }

    return {
        "net_performance": net_stats,
        "gross_performance": gross_stats,
        "cost_breakdown": cost_breakdown,
        "portfolio_diagnostics": diagnostics,
    }
