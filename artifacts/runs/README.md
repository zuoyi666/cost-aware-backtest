# Run Artifacts

Each experiment run writes into:

`artifacts/runs/exp_YYYYMMDD_name/`

This mirrors the upstream `news-to-signal` export convention so a completed upstream run directory can be handed off directly into this repo.

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
