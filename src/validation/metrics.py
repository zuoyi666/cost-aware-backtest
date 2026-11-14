from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


COST_COMPONENTS = ("commission_cost", "slippage_cost", "spread_cost", "impact_cost")


def _mark_to_market_rows(fills_df: pd.DataFrame, market_df: pd.DataFrame) -> pd.DataFrame:
    """One row per fill and held bar: the fill's gross P&L on that bar, as a fraction of capital.

    A fill holds `target_weight / entry_price` units from its entry (at `entry_price`) to its exit
    (at `exit_price`). On each bar in between it is marked at that bar's close, so the bar's P&L is
    `target_weight * (mark_t - mark_{t-1}) / entry_price`, with the entry price as the first previous
    mark and the exit price as the last mark. The bars telescope: a fill's bar P&L sums exactly to
    its `gross_pnl`. A close missing inside the holding period carries the last known close forward
    (past data only); without any close yet, the entry price is used.
    """
    schedule = pd.Index(sorted(market_df["timestamp"].drop_duplicates().tolist()))
    closes = (
        market_df.pivot_table(index="timestamp", columns="asset", values="close", aggfunc="last")
        .reindex(schedule)
        .ffill()
    )
    column_of = {asset: i for i, asset in enumerate(closes.columns)}
    close_values = closes.to_numpy(dtype=float)

    fills = fills_df.reset_index(drop=True)
    first_bar = fills["entry_bar_index"].to_numpy(dtype=int)
    n_bars = fills["exit_bar_index"].to_numpy(dtype=int) - first_bar + 1
    fill_id = np.repeat(np.arange(len(fills)), n_bars)
    offset = np.concatenate([np.arange(n) for n in n_bars])
    bar = first_bar[fill_id] + offset

    entry_price = fills["entry_price"].to_numpy(dtype=float)[fill_id]
    mark = close_values[bar, fills["asset"].map(column_of).to_numpy(dtype=int)[fill_id]]
    mark = np.where(np.isnan(mark), entry_price, mark)
    is_last = offset == n_bars[fill_id] - 1
    mark = np.where(is_last, fills["exit_price"].to_numpy(dtype=float)[fill_id], mark)
    previous = np.where(offset == 0, entry_price, np.roll(mark, 1))

    weight = fills["target_weight"].to_numpy(dtype=float)[fill_id]
    return pd.DataFrame({
        "timestamp": schedule.take(bar),
        "fill_id": fill_id,
        "gross_pnl": weight * (mark - previous) / entry_price,
    })


def build_portfolio_timeseries(fills_df: pd.DataFrame, market_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The book's P&L per bar, marked to market, and its turnover per entry bar.

    Gross P&L comes from `_mark_to_market_rows`, so overlapping cohorts each contribute on every
    bar they are held. (Booking a cohort's whole holding-period P&L on its exit bar instead
    understates the series' volatility, by up to sqrt(holding period) when signals persist, and
    overstates its Sharpe ratio by the same factor.) Costs are booked when they are paid: the entry
    part on the entry bar, the exit part on the exit bar. Every bar from the first entry to the last
    exit is a row; a bar without positions has zero P&L.
    """
    if fills_df.empty:
        empty = pd.DataFrame()
        return empty, empty

    marked = _mark_to_market_rows(fills_df, market_df)
    gross = marked.groupby("timestamp").agg(gross_pnl=("gross_pnl", "sum"), n_positions=("fill_id", "nunique"))

    entry_costs = fills_df[["entry_timestamp"] + [f"{c}_entry" for c in COST_COMPONENTS]]
    entry_costs = entry_costs.rename(columns={"entry_timestamp": "timestamp", **{f"{c}_entry": c for c in COST_COMPONENTS}})
    exit_costs = fills_df[["exit_timestamp"] + [f"{c}_exit" for c in COST_COMPONENTS]]
    exit_costs = exit_costs.rename(columns={"exit_timestamp": "timestamp", **{f"{c}_exit": c for c in COST_COMPONENTS}})
    costs = pd.concat([entry_costs, exit_costs], ignore_index=True).groupby("timestamp")[list(COST_COMPONENTS)].sum()

    schedule = pd.Index(sorted(market_df["timestamp"].drop_duplicates().tolist()))
    span = schedule[(schedule >= fills_df["entry_timestamp"].min()) & (schedule <= fills_df["exit_timestamp"].max())]
    portfolio_ts = gross.join(costs, how="outer").reindex(span).fillna(0.0)
    portfolio_ts["n_positions"] = portfolio_ts["n_positions"].astype(int)
    portfolio_ts["total_cost"] = portfolio_ts[list(COST_COMPONENTS)].sum(axis=1)
    portfolio_ts["net_pnl"] = portfolio_ts["gross_pnl"] - portfolio_ts["total_cost"]
    portfolio_ts = portfolio_ts.rename_axis("timestamp").reset_index()[
        ["timestamp", "gross_pnl", "net_pnl", "total_cost", *COST_COMPONENTS, "n_positions"]
    ]

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
        "dropped_missing_price": int(fills_df.attrs.get("dropped_missing_price", 0)),
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
