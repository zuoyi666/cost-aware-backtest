# Cross Project Conventions (Cost-Aware Backtest)

## Scope

This doc defines the conventions shared with upstream signal research projects such as `news-to-signal`.

## 1) Directory Structure

- Keep the shared structure:
  - `src/data`, `src/features`, `src/labels`, `src/models`,
    `src/validation`, `src/pipelines`, `src/utils`
  - `configs/*.yaml` for experiment parameters
  - `artifacts/runs/exp_YYYYMMDD_name/` for per-run outputs
  - `data/{raw,interim,processed}`
- Allow minimal downstream additions only when they are task-specific:
  - `src/portfolio`
  - `src/execution`

## 2) Signal Schema (Required)

- Standard columns:
  - `timestamp`
  - `asset`
  - `signal_value`
  - `signal_name`
  - `signal_version`
  - `horizon`
  - `source`
- Export default format: `parquet`
- CSV is mandatory fallback when parquet is unavailable

## 3) Artifact Layout

Every run must include at least:

- `run_config.yaml`
- `metrics.json`
- `summary.md`
- `tables/`
- `figures/`

Recommended downstream additions:

- `signals.parquet` or `signals.csv`
- `fills.parquet` or `fills.csv`
- `portfolio_timeseries.parquet` or `portfolio_timeseries.csv`

## 4) Config Convention

- Keep all experiment-relevant parameters in:
  - `configs/data.yaml`
  - `configs/features.yaml`
  - `configs/baseline.yaml`
  - `configs/experiment.yaml`
- CLI flags only override YAML defaults when explicitly provided.

## 5) Experiment Naming

- Use `exp_YYYYMMDD_name` format for deterministic baselines when needed.
- Runtime-generated names may include time for uniqueness:
  - `exp_20260323_101500_baseline`
  - `exp_20260323_101500_delay_2`
  - `exp_20260323_101500_cost_x2`

## 6) Research Output Priorities

- Prefer net-of-cost metrics over gross-only metrics in summaries.
- Persist machine-readable artifacts before notebook-level analysis.
- Keep the first version transparent and reproducible rather than over-engineered.
