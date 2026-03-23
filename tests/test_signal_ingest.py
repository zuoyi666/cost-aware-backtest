import json
from pathlib import Path

import pandas as pd

from src.data.signal_ingest import load_signals_from_config


def test_load_signals_from_news_to_signal_run_dir(tmp_path):
    run_dir = tmp_path / "upstream_project" / "artifacts" / "runs" / "exp_test"
    run_dir.mkdir(parents=True)

    signals = pd.DataFrame(
        [
            {
                "timestamp": "2026-03-05 00:00:00",
                "asset": "AAPL",
                "signal_value": 1.5,
                "signal_name": "signal_full",
                "signal_version": "v1",
                "horizon": 5,
                "source": "news-to-signal",
            }
        ]
    )
    signals_path = run_dir / "signals.csv"
    signals.to_csv(signals_path, index=False)

    manifest = {
        "file": {
            "format": "csv",
            "path": "artifacts/runs/exp_test/signals.csv",
        }
    }
    (run_dir / "signals_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    signal_df, metadata = load_signals_from_config(
        {
            "data": {
                "signal_path": str(run_dir),
                "signal_format": "auto",
            },
            "features": {
                "signal_name": "signal_full",
                "signal_version": "v1",
                "horizon": "5",
                "source": "news-to-signal",
            },
        }
    )

    assert metadata["signal_input_kind"] == "news_to_signal_run_dir"
    assert Path(metadata["resolved_signal_path"]) == signals_path
    assert signal_df.loc[0, "horizon"] == "5"
