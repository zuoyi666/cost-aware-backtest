from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from src.data.market_data import filter_market_data_frame, load_market_data_frame
from src.data.signal_ingest import apply_signal_data_filters, build_signal_coverage_table, load_signals_from_config
from src.execution.costs import apply_transaction_costs
from src.execution.delay import resolve_execution_fills
from src.portfolio.construction import construct_target_weights
from src.utils.artifacts import write_json_file, write_markdown_file, write_table, write_yaml_file
from src.utils.configuration import load_pipeline_config
from src.utils.experiment import make_run_dir, make_run_name
from src.utils.signal_schema import write_signal_snapshot
from src.validation.metrics import build_portfolio_timeseries, compute_metrics_payload
from src.validation.robustness import (
    build_robustness_scenarios,
    finalize_robustness_comparison,
    render_robustness_summary_markdown,
)


def _resolve_project_path(project_root: str, path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return Path(project_root) / path


def _load_market_data_from_config(config: Dict[str, Any]) -> pd.DataFrame:
    data_cfg = config.get("data", {})
    project_root = config.get("project_root", str(Path.cwd()))
    market_path = _resolve_project_path(project_root, data_cfg["market_data_path"])
    market_df = load_market_data_frame(
        market_path,
        file_format=data_cfg.get("market_data_format", "auto"),
    )
    return filter_market_data_frame(
        market_df,
        start=data_cfg.get("start"),
        end=data_cfg.get("end"),
    )


def run_backtest_core(
    signal_df: pd.DataFrame,
    market_df: pd.DataFrame,
    config: Dict[str, Any],
) -> Dict[str, pd.DataFrame]:
    execution_cfg = config.get("baseline", {}).get("execution", {})
    holding_period_bars = int(execution_cfg.get("holding_period_bars", 1))

    weights_df = construct_target_weights(
        signal_df,
        portfolio_cfg=config.get("baseline", {}).get("portfolio", {}),
        holding_period_bars=holding_period_bars,
    )
    if weights_df.empty:
        raise ValueError("No tradable cohorts were generated from the configured signal universe.")

    fills_df = resolve_execution_fills(weights_df, market_df, execution_cfg)
    if fills_df.empty:
        raise ValueError("No executable fills were generated after applying delay and market alignment.")

    fills_df = apply_transaction_costs(
        fills_df,
        cost_cfg=config.get("baseline", {}).get("costs", {}),
    )
    portfolio_ts, turnover_ts = build_portfolio_timeseries(fills_df)
    return {
        "weights": weights_df,
        "fills": fills_df,
        "portfolio_timeseries": portfolio_ts,
        "turnover_timeseries": turnover_ts,
    }


def _extract_robustness_metrics(scenario: Dict[str, Any], metrics_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "scenario": scenario["name"],
        "group": scenario["group"],
        "dimension": scenario["dimension"],
        "value": scenario["value"],
        "description": scenario["description"],
        "status": "ok",
        "net_total_return": metrics_payload["net_performance"]["total_return"],
        "annualized_net_return": metrics_payload["net_performance"]["annualized_return"],
        "net_sharpe_ratio": metrics_payload["net_performance"]["sharpe_ratio"],
        "net_max_drawdown": metrics_payload["net_performance"]["max_drawdown"],
        "gross_total_return": metrics_payload["gross_performance"]["total_return"],
        "gross_sharpe_ratio": metrics_payload["gross_performance"]["sharpe_ratio"],
        "total_cost": metrics_payload["cost_breakdown"]["total_cost"],
        "turnover_total": metrics_payload["portfolio_diagnostics"]["turnover_total"],
        "signal_assets": metrics_payload["portfolio_diagnostics"]["signal_assets"],
        "tradable_cohorts": metrics_payload["portfolio_diagnostics"]["tradable_cohorts"],
        "fills": metrics_payload["portfolio_diagnostics"]["fills"],
    }


def run_robustness_analysis(
    signal_df: pd.DataFrame,
    market_df: pd.DataFrame,
    base_config: Dict[str, Any],
) -> pd.DataFrame:
    rows = []
    for scenario in build_robustness_scenarios(base_config):
        try:
            scenario_signal_df = apply_signal_data_filters(signal_df, scenario["config"].get("data", {}))
            if scenario_signal_df.empty:
                raise ValueError("No signals remain after applying scenario-level data filters.")
            scenario_market_df = market_df[market_df["asset"].isin(scenario_signal_df["asset"].unique())].copy()

            outputs = run_backtest_core(scenario_signal_df, scenario_market_df, scenario["config"])
            metrics_payload = compute_metrics_payload(
                signal_df=scenario_signal_df,
                weights_df=outputs["weights"],
                fills_df=outputs["fills"],
                portfolio_ts=outputs["portfolio_timeseries"],
                turnover_ts=outputs["turnover_timeseries"],
                config=scenario["config"],
            )
            rows.append(
                _extract_robustness_metrics(scenario, metrics_payload)
            )
        except Exception as exc:
            rows.append(
                {
                    "scenario": scenario["name"],
                    "group": scenario["group"],
                    "dimension": scenario["dimension"],
                    "value": scenario["value"],
                    "description": scenario["description"],
                    "status": f"failed: {exc}",
                }
            )
    return finalize_robustness_comparison(pd.DataFrame(rows))


def _best_robustness_row(robustness_df: pd.DataFrame) -> Dict[str, Any] | None:
    if robustness_df.empty or "net_sharpe_ratio" not in robustness_df.columns:
        return None
    candidates = robustness_df.dropna(subset=["net_sharpe_ratio"]).copy()
    non_base = candidates[candidates["scenario"] != "base_case"].copy()
    if not non_base.empty:
        candidates = non_base
    if candidates.empty:
        return None
    row = candidates.sort_values("net_sharpe_ratio", ascending=False).iloc[0]
    return row.to_dict()


def render_summary_markdown(
    config: Dict[str, Any],
    metrics_payload: Dict[str, Any],
    robustness_df: pd.DataFrame,
) -> str:
    run_cfg = config["run"]
    features_cfg = config.get("features", {})
    run_metadata = metrics_payload.get("run_metadata", {})
    best_robustness = _best_robustness_row(robustness_df)

    lines = [
        "# Experiment Summary",
        "",
        f"- Run: `{run_cfg['run_name']}`",
        f"- Timestamp (UTC): `{run_cfg['timestamp_utc']}`",
        f"- Signal: `{features_cfg.get('signal_name', '')}`",
        f"- Signal version: `{features_cfg.get('signal_version', '')}`",
        f"- Horizon: `{features_cfg.get('horizon', '')}`",
        f"- Source: `{features_cfg.get('source', '')}`",
        f"- Signal input kind: `{run_metadata.get('signal_input_kind', 'standard_signal_file')}`",
        "",
        "## Net Performance",
        f"- total_return: `{metrics_payload['net_performance']['total_return']}`",
        f"- annualized_return: `{metrics_payload['net_performance']['annualized_return']}`",
        f"- sharpe_ratio: `{metrics_payload['net_performance']['sharpe_ratio']}`",
        f"- max_drawdown: `{metrics_payload['net_performance']['max_drawdown']}`",
        "",
        "## Cost Breakdown",
        f"- total_cost: `{metrics_payload['cost_breakdown']['total_cost']}`",
        f"- spread_cost: `{metrics_payload['cost_breakdown']['spread_cost']}`",
        f"- slippage_cost: `{metrics_payload['cost_breakdown']['slippage_cost']}`",
        f"- commission_cost: `{metrics_payload['cost_breakdown']['commission_cost']}`",
        "",
        "## Portfolio Diagnostics",
        f"- fills: `{metrics_payload['portfolio_diagnostics']['fills']}`",
        f"- turnover_total: `{metrics_payload['portfolio_diagnostics']['turnover_total']}`",
        f"- tradable_cohorts: `{metrics_payload['portfolio_diagnostics']['tradable_cohorts']}`",
        "",
    ]

    if run_metadata.get("upstream_run_dir"):
        lines.extend(
            [
                "## Upstream Integration",
                f"- upstream_run_dir: `{run_metadata['upstream_run_dir']}`",
                f"- resolved_signal_path: `{run_metadata.get('resolved_signal_path', '')}`",
                "",
            ]
        )

    if best_robustness:
        lines.extend(
            [
                "## Best Robustness Scenario",
                f"- scenario: `{best_robustness['scenario']}`",
                f"- dimension: `{best_robustness['dimension']}`",
                f"- value: `{best_robustness['value']}`",
                f"- net_sharpe_ratio: `{best_robustness['net_sharpe_ratio']}`",
                f"- net_total_return: `{best_robustness['net_total_return']}`",
            ]
        )
    else:
        lines.extend(["## Best Robustness Scenario", "- No successful robustness scenario was produced."])

    return "\n".join(lines) + "\n"


def generate_figures(
    run_dir: Path,
    portfolio_ts: pd.DataFrame,
    turnover_ts: pd.DataFrame,
    fills_df: pd.DataFrame,
) -> None:
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    if not portfolio_ts.empty:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(portfolio_ts["timestamp"], portfolio_ts["gross_cumulative_return"], label="gross")
        ax.plot(portfolio_ts["timestamp"], portfolio_ts["net_cumulative_return"], label="net")
        ax.set_title("Equity Curve")
        ax.set_ylabel("Cumulative Return")
        ax.legend()
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(figures_dir / "equity_curve.png", dpi=150)
        plt.close(fig)

    if not fills_df.empty:
        totals = {
            "commission": fills_df["commission_cost"].sum(),
            "slippage": fills_df["slippage_cost"].sum(),
            "spread": fills_df["spread_cost"].sum(),
            "impact": fills_df["impact_cost"].sum(),
        }
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(list(totals.keys()), list(totals.values()))
        ax.set_title("Transaction Cost Breakdown")
        ax.set_ylabel("Cost")
        fig.tight_layout()
        fig.savefig(figures_dir / "cost_breakdown.png", dpi=150)
        plt.close(fig)

    if not turnover_ts.empty:
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(turnover_ts["timestamp"], turnover_ts["turnover"])
        ax.set_title("Turnover Time Series")
        ax.set_ylabel("Turnover")
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(figures_dir / "turnover_series.png", dpi=150)
        plt.close(fig)


def run_experiment(
    experiment_name: str,
    run_name: str | None = None,
    config_dir: str = "configs",
    config_overrides: Dict[str, Any] | None = None,
    output_root: str | None = None,
) -> Dict[str, Any]:
    overrides = deepcopy(config_overrides or {})
    overrides.setdefault("experiment", {})["name"] = experiment_name
    if run_name is not None:
        overrides["experiment"]["run_name"] = run_name

    config = load_pipeline_config(config_dir=config_dir, overrides=overrides)
    resolved_run_name = config["experiment"].get("run_name") or make_run_name(experiment_name)
    project_root = config.get("project_root", str(Path.cwd()))
    resolved_output_root = output_root or config.get("experiment", {}).get("output", {}).get("root", "artifacts/runs")
    run_root_path = _resolve_project_path(project_root, resolved_output_root)
    run_dir = make_run_dir(str(run_root_path), resolved_run_name)

    config["data"]["signal_path"] = str(_resolve_project_path(project_root, config["data"]["signal_path"]))
    config["data"]["market_data_path"] = str(_resolve_project_path(project_root, config["data"]["market_data_path"]))
    config["run"] = {
        "name": experiment_name,
        "run_name": resolved_run_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": project_root,
    }

    signal_df, signal_input_meta = load_signals_from_config(config)
    config["data"]["signal_input_kind"] = signal_input_meta["signal_input_kind"]
    config["data"]["resolved_signal_path"] = signal_input_meta["resolved_signal_path"]
    config["data"]["resolved_signal_format"] = signal_input_meta["resolved_signal_format"]
    if signal_input_meta.get("signal_manifest_path"):
        config["data"]["signal_manifest_path"] = signal_input_meta["signal_manifest_path"]
    if signal_input_meta.get("upstream_run_dir"):
        config["data"]["upstream_run_dir"] = signal_input_meta["upstream_run_dir"]
    market_df = _load_market_data_from_config(config)
    outputs = run_backtest_core(signal_df, market_df, config)

    metrics_payload = compute_metrics_payload(
        signal_df=signal_df,
        weights_df=outputs["weights"],
        fills_df=outputs["fills"],
        portfolio_ts=outputs["portfolio_timeseries"],
        turnover_ts=outputs["turnover_timeseries"],
        config=config,
    )

    robustness_df = run_robustness_analysis(signal_df, market_df, config)
    metrics_payload["robustness"] = robustness_df.to_dict(orient="records")
    metrics_payload["run_metadata"] = {
        "name": experiment_name,
        "run_name": resolved_run_name,
        "signal_name": config["features"].get("signal_name"),
        "signal_version": config["features"].get("signal_version"),
        "signal_path": config["data"]["signal_path"],
        "market_data_path": config["data"]["market_data_path"],
        "signal_input_kind": signal_input_meta["signal_input_kind"],
        "resolved_signal_path": signal_input_meta["resolved_signal_path"],
        "resolved_signal_format": signal_input_meta["resolved_signal_format"],
        "signal_manifest_path": signal_input_meta.get("signal_manifest_path"),
        "upstream_run_dir": signal_input_meta.get("upstream_run_dir"),
    }

    signal_snapshot = write_signal_snapshot(signal_df, run_dir)
    fills_path = write_table(outputs["fills"], run_dir / "fills")
    portfolio_path = write_table(outputs["portfolio_timeseries"], run_dir / "portfolio_timeseries")
    turnover_path = write_table(outputs["turnover_timeseries"], run_dir / "tables" / "turnover_timeseries")
    coverage_path = write_table(build_signal_coverage_table(signal_df), run_dir / "tables" / "signal_coverage")
    robustness_path = write_table(robustness_df, run_dir / "tables" / "robustness_comparison")

    summary_md = render_summary_markdown(config, metrics_payload, robustness_df)
    robustness_summary_md = render_robustness_summary_markdown(config, robustness_df)
    generate_figures(
        run_dir=run_dir,
        portfolio_ts=outputs["portfolio_timeseries"],
        turnover_ts=outputs["turnover_timeseries"],
        fills_df=outputs["fills"],
    )

    run_config_path = write_yaml_file(run_dir / "run_config.yaml", config)
    metrics_path = write_json_file(run_dir / "metrics.json", metrics_payload)
    summary_path = write_markdown_file(run_dir / "summary.md", summary_md)
    robustness_summary_path = write_markdown_file(run_dir / "reports" / "robustness_summary.md", robustness_summary_md)

    return {
        "run_name": resolved_run_name,
        "run_dir": str(run_dir),
        "run_config": str(run_config_path),
        "metrics": str(metrics_path),
        "summary": str(summary_path),
        "signals": signal_snapshot["signal_file"],
        "signal_manifest": signal_snapshot["manifest"],
        "fills": str(fills_path),
        "portfolio_timeseries": str(portfolio_path),
        "turnover_timeseries": str(turnover_path),
        "signal_coverage": str(coverage_path),
        "robustness": str(robustness_path),
        "robustness_summary": str(robustness_summary_path),
    }
