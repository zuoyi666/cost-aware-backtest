from __future__ import annotations

import argparse
import json

from src.pipelines.run_plan import run_from_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cost-aware backtest research runner")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a full backtest experiment")
    run_p.add_argument("--experiment-name", default="baseline")
    run_p.add_argument("--run-name", default=None)
    run_p.add_argument("--config-dir", default="configs")
    run_p.add_argument("--run-root", default=None)
    run_p.add_argument("--signal-path", default=None)
    run_p.add_argument("--market-data-path", default=None)
    run_p.add_argument("--signal-name", default=None)
    run_p.add_argument("--signal-version", default=None)
    run_p.add_argument("--horizon", default=None)
    run_p.add_argument("--start", default=None)
    run_p.add_argument("--end", default=None)
    run_p.add_argument("--delay-bars", type=int, default=None)
    run_p.add_argument("--holding-period-bars", type=int, default=None)
    run_p.add_argument("--bars-per-day", type=int, default=None)
    run_p.add_argument("--top-n", type=int, default=None)
    run_p.add_argument("--cost-multiplier", type=float, default=None)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        result = run_from_cli(args)
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
