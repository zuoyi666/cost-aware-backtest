import pandas as pd

from src.pipelines.backtest_pipeline import render_summary_markdown


def _summary(robustness_df):
    config = {"run": {"run_name": "exp_test", "timestamp_utc": "2026-10-24T00:00:00Z"}, "features": {}}
    metrics = {
        "net_performance": {"total_return": 0.01, "annualized_return": 0.1, "sharpe_ratio": 0.5, "max_drawdown": -0.02},
        "cost_breakdown": {"total_cost": 0.001, "spread_cost": 0.0, "slippage_cost": 0.0005, "commission_cost": 0.0005},
        "portfolio_diagnostics": {"fills": 10, "turnover_total": 2.0, "tradable_cohorts": 5},
    }
    return render_summary_markdown(config, metrics, robustness_df)


def test_summary_reports_every_robustness_scenario_without_picking_a_best():
    robustness = pd.DataFrame(
        [
            {"scenario": "delay_plus_1", "net_sharpe_ratio": 2.5, "net_total_return": 0.03},
            {"scenario": "base_case", "net_sharpe_ratio": 0.5, "net_total_return": 0.01},
            {"scenario": "fees_x2", "status": "failed: no fills"},
        ]
    )
    text = _summary(robustness)
    assert "Best Robustness" not in text
    for name in ["base_case", "delay_plus_1", "fees_x2"]:
        assert f"`{name}`" in text
    # The base case is the primary result and is listed first.
    assert text.index("`base_case`") < text.index("`delay_plus_1`")
    assert "failed: no fills" in text


def test_summary_states_the_cost_netting_assumption():
    text = _summary(pd.DataFrame(columns=["scenario"]))
    assert "not netted" in text
    assert "No robustness scenario was produced." in text
