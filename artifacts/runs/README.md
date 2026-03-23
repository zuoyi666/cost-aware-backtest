# Run Artifacts

Each experiment run writes into:

`artifacts/runs/exp_YYYYMMDD_name/`

Minimum standardized outputs:

- `run_config.yaml`
- `metrics.json`
- `summary.md`
- `figures/`
- `tables/`

Common additional outputs:

- `signals.parquet` or `signals.csv`
- `fills.parquet` or `fills.csv`
- `portfolio_timeseries.parquet` or `portfolio_timeseries.csv`

Generated run directories are local research outputs and are intentionally ignored by `.gitignore` for GitHub publishing. Keep this README; do not commit per-run outputs unless you intentionally want to publish a frozen example run.
