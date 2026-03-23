import json
from pathlib import Path

from src.pipelines.backtest_pipeline import run_experiment


def test_run_experiment_end_to_end(tmp_path, monkeypatch):
    project_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project_root)

    result = run_experiment(
        experiment_name="baseline",
        config_dir="configs",
        output_root=str(tmp_path / "runs"),
    )

    metrics = json.loads(Path(result["metrics"]).read_text(encoding="utf-8"))
    summary_path = Path(result["summary"])

    assert Path(result["run_config"]).exists()
    assert summary_path.exists()
    assert Path(result["fills"]).exists()
    assert Path(result["portfolio_timeseries"]).exists()
    assert Path(result["signal_coverage"]).exists()
    assert Path(result["robustness"]).exists()
    assert Path(result["robustness_summary"]).exists()
    assert "net_performance" in metrics
    assert "cost_breakdown" in metrics
    assert metrics["portfolio_diagnostics"]["fills"] > 0
    scenario_names = {row["scenario"] for row in metrics["robustness"]}
    assert {
        "base_case",
        "delay_plus_1",
        "delay_plus_2",
        "fees_x2",
        "slippage_x2",
        "smaller_universe",
    }.issubset(scenario_names)
    robustness_by_name = {row["scenario"]: row for row in metrics["robustness"]}
    assert robustness_by_name["smaller_universe"]["signal_assets"] < robustness_by_name["base_case"]["signal_assets"]
