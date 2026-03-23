# GitHub Publish Checklist

## Commit

- source code under `src/`
- `cli.py`
- `configs/`
- `tests/`
- `README.md`
- `LICENSE`
- `pyproject.toml`
- `requirements.txt`
- `cross_project_conventions.md`
- small deterministic demo data under `data/processed/`
- reference files under `data/reference/`
- `artifacts/runs/README.md`
- `.gitignore`

## Do Not Commit

- generated run outputs under `artifacts/runs/<run_name>/`
- `.pytest_cache/`
- `__pycache__/`
- local notes such as `task_plan.md`, `findings.md`, `progress.md`
- raw staging data under `data/raw/`
- intermediate staging data under `data/interim/`
- large local binary exports

## Pre-Push Checks

- run `pytest -q`
- preview `README.md`
- confirm sample data is deterministic and small
- confirm no generated run directory is staged
- confirm the upstream repository link placeholder was replaced
- confirm the chosen GitHub repo visibility and license are correct
