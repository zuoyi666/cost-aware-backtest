"""Mark-to-market P&L, cost timing, square-root impact and dropped fills."""
import math

import numpy as np
import pandas as pd
import pytest

from src.execution.costs import apply_transaction_costs
from src.execution.delay import resolve_execution_fills
from src.portfolio.construction import construct_target_weights
from src.validation.metrics import _mark_to_market_rows, build_portfolio_timeseries, compute_metrics_payload

EXECUTION = {"delay_bars": 1, "holding_period_bars": 5, "entry_price": "open", "exit_price": "close"}


def _market(n_assets=20, n_bars=600, seed=0, drift=None):
    rng = np.random.default_rng(seed)
    assets = [f"A{i:02d}" for i in range(n_assets)]
    stamps = pd.bdate_range("2020-01-01", periods=n_bars)
    returns = rng.normal(0.0, 0.01, (n_bars, n_assets)) + (0.0 if drift is None else drift)
    close = 100.0 * np.cumprod(1.0 + returns, axis=0)
    open_ = np.vstack([close[0], close[:-1]])
    market = pd.DataFrame({
        "timestamp": np.repeat(stamps, n_assets), "asset": assets * n_bars,
        "open": open_.ravel(), "close": close.ravel(), "volume": 1e6, "adv": 1e6,
        "spread_bps": 4.0, "volatility_20d": 0.01,
    })
    return market, assets, stamps, returns


def _signals(assets, stamps, values):
    return pd.DataFrame({
        "timestamp": np.repeat(stamps, len(assets)), "asset": assets * len(stamps),
        "signal_value": np.tile(values, len(stamps)), "signal_name": "s", "signal_version": "v1",
        "horizon": "5", "source": "test",
    })


def _run(market, signals, costs=None):
    weights = construct_target_weights(signals, {"top_n": 4, "min_assets": 8, "gross_leverage": 1.0}, 5)
    fills = apply_transaction_costs(resolve_execution_fills(weights, market, EXECUTION), costs or {})
    return weights, fills


def test_bar_pnl_telescopes_to_each_fill_gross_pnl():
    market, assets, stamps, _ = _market()
    rng = np.random.default_rng(1)
    signals = _signals(assets, stamps, rng.standard_normal(len(assets)))
    signals["signal_value"] = rng.standard_normal(len(signals))          # a fresh ranking every bar
    _, fills = _run(market, signals)
    marked = _mark_to_market_rows(fills, market)
    per_fill = marked.groupby("fill_id")["gross_pnl"].sum().to_numpy()
    assert np.allclose(per_fill, fills["gross_pnl"].to_numpy(), atol=1e-15)
    assert (marked.groupby("fill_id").size() == 5).all()


def test_costs_split_into_entry_and_exit_parts_and_are_booked_once():
    market, assets, stamps, _ = _market()
    signals = _signals(assets, stamps, np.random.default_rng(2).standard_normal(len(assets)))
    _, fills = _run(market, signals, {"commission_bps": 1.0, "slippage_bps": 3.0, "half_spread_bps": 2.0})
    for component in ("commission_cost", "slippage_cost", "spread_cost", "impact_cost"):
        assert np.allclose(fills[component], fills[f"{component}_entry"] + fills[f"{component}_exit"])
    expected = fills["target_weight"].abs() * (2 * 1.0 + 2 * 3.0 + 4.0) / 10000.0   # 4 bps quoted spread, half each side
    assert np.allclose(fills["total_cost"], expected)
    portfolio, _ = build_portfolio_timeseries(fills, market)
    assert portfolio["total_cost"].sum() == pytest.approx(fills["total_cost"].sum())
    assert portfolio["gross_pnl"].sum() == pytest.approx(fills["gross_pnl"].sum())


def test_persistent_signal_volatility_matches_the_held_book():
    """With the same ranking every bar the book holds one fixed long-short portfolio, so its daily
    volatility is that portfolio's. Booking each cohort on its exit bar showed about 1/sqrt(5) of it."""
    market, assets, stamps, returns = _market(n_bars=1500)
    score = np.random.default_rng(3).standard_normal(len(assets))
    weights, fills = _run(market, _signals(assets, stamps, score))
    portfolio, _ = build_portfolio_timeseries(fills, market)
    book = weights[weights["signal_timestamp"] == stamps[0]].set_index("asset")["target_weight"] * 5
    held = pd.Series(returns @ book.reindex(assets).fillna(0.0).to_numpy(), index=stamps)
    steady = portfolio.set_index("timestamp")["gross_pnl"].iloc[10:-10]
    ratio = steady.std() / held.loc[steady.index].std()
    assert 0.9 < ratio < 1.1


def test_square_root_impact_has_explicit_units():
    market, assets, stamps, _ = _market()
    signals = _signals(assets, stamps, np.random.default_rng(4).standard_normal(len(assets)))
    _, fills = _run(market, signals, {"impact_coefficient": 1.0, "book_notional": 1_000_000.0})
    row = fills.iloc[0]
    participation = abs(row["target_weight"]) * 1_000_000.0 / (row["entry_adv"] * row["entry_price"])
    per_side = abs(row["target_weight"]) * 1.0 * 0.01 * math.sqrt(participation)
    assert row["impact_cost_entry"] == pytest.approx(per_side)
    assert row["impact_cost"] == pytest.approx(2 * per_side)


def test_missing_exit_prices_are_counted_not_hidden():
    market, assets, stamps, _ = _market()
    signals = _signals(assets, stamps, np.linspace(1.0, -1.0, len(assets)))   # the first names are always held long
    gone = market["asset"].isin(assets[:3]) & (market["timestamp"] >= stamps[300])
    weights, fills = _run(market[~gone], signals)
    assert fills.attrs["dropped_missing_price"] > 0
    portfolio, turnover = build_portfolio_timeseries(fills, market[~gone])
    config = {"baseline": {"execution": EXECUTION, "portfolio": {}, "metrics": {"bars_per_day": 1}}}
    payload = compute_metrics_payload(signals, weights, fills, portfolio, turnover, config)
    assert payload["portfolio_diagnostics"]["dropped_missing_price"] == fills.attrs["dropped_missing_price"]
