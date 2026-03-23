from __future__ import annotations

from typing import Any, Dict

from src.pipelines.backtest_pipeline import run_experiment


def run_from_cli(args) -> Dict[str, Any]:
    overrides: Dict[str, Any] = {}
    if args.signal_path is not None:
        overrides.setdefault("data", {})["signal_path"] = args.signal_path
    if args.market_data_path is not None:
        overrides.setdefault("data", {})["market_data_path"] = args.market_data_path
    if args.signal_name is not None:
        overrides.setdefault("features", {})["signal_name"] = args.signal_name
    if args.signal_version is not None:
        overrides.setdefault("features", {})["signal_version"] = args.signal_version
    if args.horizon is not None:
        overrides.setdefault("features", {})["horizon"] = args.horizon
    if args.start is not None:
        overrides.setdefault("data", {})["start"] = args.start
    if args.end is not None:
        overrides.setdefault("data", {})["end"] = args.end
    if args.delay_bars is not None:
        overrides.setdefault("baseline", {}).setdefault("execution", {})["delay_bars"] = args.delay_bars
    if args.holding_period_bars is not None:
        overrides.setdefault("baseline", {}).setdefault("execution", {})["holding_period_bars"] = args.holding_period_bars
    if args.bars_per_day is not None:
        overrides.setdefault("baseline", {}).setdefault("metrics", {})["bars_per_day"] = args.bars_per_day
    if args.top_n is not None:
        overrides.setdefault("baseline", {}).setdefault("portfolio", {})["top_n"] = args.top_n
    if args.cost_multiplier is not None:
        overrides.setdefault("baseline", {}).setdefault("costs", {})["cost_multiplier"] = args.cost_multiplier

    return run_experiment(
        experiment_name=args.experiment_name,
        run_name=args.run_name,
        config_dir=args.config_dir,
        config_overrides=overrides,
        output_root=args.run_root,
    )
