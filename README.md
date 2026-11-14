# Cost-Aware Backtest

Config-driven, cost-aware backtesting for standardized cross-sectional equity signals.

This repository is the downstream execution layer for signal research projects such as `news-to-signal`. It ingests standardized signal files, applies a simple but explicit portfolio construction and execution model, and writes reproducible run artifacts for comparison across experiments.

> **Status:** a finished prototype. It makes no performance claims: the bundled data is a small fixture built to exercise the pipeline.

## What this project does

- reads external signals using a standardized long-format schema
- constructs a basic long-short portfolio from signal ranks
- applies delayed execution and a transparent transaction cost model
- reports gross and net performance separately
- writes machine-readable artifacts for every run

## Why it matters

For a quant research portfolio, a signal file is not enough. A strong research story should show:

- how signals are consumed downstream
- what execution assumptions are being made
- how much performance survives after costs
- whether results are reproducible and comparable across runs

This repo is intentionally small. It is an MVP focused on clarity, reproducibility, and clean handoff from upstream signal research.

## Relationship to news-to-signal

`news-to-signal` is the upstream research project that generates standardized signal exports from financial news features. This repository is the downstream backtest layer.

Upstream repository link:

- [news-to-signal](https://github.com/zuoyi666/news-to-signal)

## Known limitations at a glance

- No netting across overlapping cohorts, so costs are conservative.
- Price returns only: no dividends, short borrow cost or payment-in-lieu.
- Deterministic sample and fixture data, not exchange-quality history.
- One signal per run; outputs illustrate the mechanics and are not performance claims.

Details are under [Current limitations](#current-limitations) below.

## How returns and costs are measured

- **Timing.** A timestamp marks a bar. A signal stamped with bar t may use information up to the end of bar t, so the default `delay_bars: 1` enters at the next bar's open. `delay_bars: 0` is only safe if the signal is known before its own bar opens.
- **Overlapping holdings.** Each signal bar starts a cohort that holds `1 / holding_period_bars` of the gross leverage, so with H overlapping cohorts the book's gross leverage stays at the target.
- **Marked to market.** Every position is marked at the close of each bar it is held, and the book's P&L is summed per bar. Booking a cohort's whole holding-period P&L on its exit bar instead would understate volatility, by up to sqrt(H) when the signal persists, and overstate the Sharpe ratio by the same factor; `tests/test_mark_to_market.py` checks this.
- **Costs.** Commission and slippage per side, half the quoted spread at entry and at exit, each booked on the bar it is paid. An optional square-root impact term, off by default: per side, `impact_coefficient × daily volatility × sqrt(traded notional / ADV notional)`, with traded notional `|weight| × book_notional` and ADV notional the entry bar's ADV in shares times its entry price.
- **Missing prices.** A fill without an entry or exit price (a halt, a delisting, a data gap) is dropped. The count is reported as `dropped_missing_price`, because a dropped exit can hide a loss.

## End-to-End Workflow

1. Research and construct standardized signals in `news-to-signal`.
2. Export a standardized run artifact under `artifacts/runs/exp_YYYYMMDD_name/`.
3. Consume that artifact here for cost-aware validation under explicit portfolio construction and execution assumptions.

The integration is kept deliberately small:

- this repo accepts a `news-to-signal` run directory, `signals_manifest.json`, or direct `signals.parquet` / `signals.csv`
- the adapter only resolves paths and normalizes light formatting differences
- the core backtest engine does not need to know anything about the upstream project internals

### Integration with news-to-signal

The current adapter supports these upstream input forms:

- `../news-to-signal/artifacts/runs/<run_name>/`
- `../news-to-signal/artifacts/runs/<run_name>/signals_manifest.json`
- `../news-to-signal/artifacts/runs/<run_name>/signals.parquet`
- `../news-to-signal/artifacts/runs/<run_name>/signals.csv`

Adapter behavior:

- resolves manifest-relative paths into the actual exported signal file
- resolves a run directory into the exported signal file automatically
- preserves the standardized column contract
- coerces `horizon` into the backtest repo's filter-friendly string representation
- fails fast on malformed required values or duplicate downstream signal keys

Example upstream-backed run:

```bash
python cli.py run \
  --experiment-name news_to_signal_integration \
  --run-name exp_20260323_news_to_signal_signal_full \
  --signal-path ../news-to-signal/artifacts/runs/exp_20260319_004234_baseline \
  --market-data-path data/processed/news_to_signal_market_data.csv \
  --signal-name signal_full \
  --signal-version v1 \
  --horizon 5 \
  --bars-per-day 1 \
  --start 2026-03-05 \
  --end 2026-03-11
```

## Standardized signal schema contract

Required columns:

- `timestamp`: signal timestamp
- `asset`: tradable asset identifier
- `signal_value`: numeric cross-sectional signal value
- `signal_name`: signal family or variant name
- `signal_version`: version tag for the signal definition
- `horizon`: holding horizon metadata from upstream research
- `source`: upstream project or dataset source

Preferred storage format:

- `parquet`
- CSV fallback when parquet is unavailable

The backtest repo treats this schema as the stable contract between upstream signal research and downstream execution research.

Path resolution and light type normalization are handled in the adapter layer. Malformed required values or duplicate downstream signal keys are treated as contract violations rather than repaired silently.

## Market data contract

Required columns:

- `timestamp`
- `asset`
- `open`
- `close`

Optional columns used by the cost model:

- `volume`
- `adv`
- `spread_bps`
- `volatility_20d`

## Install

Python `>=3.9` is expected.

```bash
python -m pip install -r requirements.txt
```

Optional verification:

```bash
pytest -q
```

## Run the sample experiment

The repo includes deterministic sample data for a reproducible smoke test:

- `data/processed/sample_signals.csv`
- `data/processed/sample_market_data.csv`

Run the default sample experiment:

```bash
python cli.py run --experiment-name baseline
```

The sample has 6 assets and 72 hourly bars, and its prices are built so that the signal ranks the next bars' returns. The run therefore prints a Sharpe ratio above 100. That number only shows that the pieces connect; `summary.md` says so in its first line.

## Generated artifacts

Each run writes to:

`artifacts/runs/exp_YYYYMMDD_name/`

Standard outputs:

- `run_config.yaml`
- `metrics.json`
- `summary.md`
- `figures/`
- `tables/`

Common machine-readable outputs:

- `signals.parquet` or `signals.csv`
- `fills.parquet` or `fills.csv`
- `portfolio_timeseries.parquet` or `portfolio_timeseries.csv`
- `tables/signal_coverage.*`
- `tables/robustness_comparison.*`
- `tables/turnover_timeseries.*`

## Robustness Checks

Each run also evaluates a small standardized robustness set:

- base case
- execution delay `+1`
- execution delay `+2`
- fees `x2`
- slippage `x2`
- smaller-universe stress (the assets with the most signal coverage over the whole sample; this uses full-sample information, so it is a stress test, not a tradable universe)

The comparison outputs are written to:

- `artifacts/runs/<run_name>/tables/robustness_comparison.*`
- `artifacts/runs/<run_name>/reports/robustness_summary.md`

This layer is intentionally small. It is meant to show implementation sensitivity and research discipline, not to turn the project into a large scenario engine.

## Data and artifact policy

Files that are reasonable to commit:

- source code
- configs
- tests
- small deterministic sample CSV files under `data/processed/`
- reference files under `data/reference/`
- documentation files such as `artifacts/runs/README.md`

Files that should stay local:

- generated run outputs under `artifacts/runs/<run_name>/`
- temporary caches such as `.pytest_cache/` and `__pycache__/`
- raw data drops under `data/raw/`
- intermediate data products under `data/interim/`
- large local binary exports

This mirrors the upstream `news-to-signal` publishing policy: keep the artifact contract documentation, keep per-run outputs local by default.

See [GITHUB_PUBLISH_CHECKLIST.md](GITHUB_PUBLISH_CHECKLIST.md) for a short pre-push checklist.

## Current limitations

- The execution model is intentionally simple and transparent, not a full production simulator.
- Costs are charged as a full round trip on each cohort's target weight. Overlapping cohorts are not netted against each other, so with persistent signals turnover and costs are overstated (a conservative bias).
- Price returns only: no dividends, short borrow cost or payment-in-lieu.
- Fills with a missing entry or exit price are dropped and counted, not repaired.
- `summary.md` lists every robustness scenario, with the base case as the primary result; no scenario is singled out as the best.
- The current sample experiment uses deterministic fixture data rather than historical exchange-quality intraday data.
- The upstream integration example uses a real `news-to-signal` signal export but a deterministic aligned market-data fixture.
- One run evaluates one `signal_name` at a time.
- This project prioritizes clean research plumbing over advanced market microstructure modeling.
