import pandas as pd

from src.utils.signal_schema import REQUIRED_SIGNAL_COLUMNS, to_standard_signal_long_format, validate_standard_signal_schema


def test_standard_signal_schema_shape():
    df = pd.DataFrame(
        [
            {"date": "2026-01-02", "ticker": "AAPL", "signal_fast": 0.1, "signal_slow": 0.5},
            {"date": "2026-01-03", "ticker": "MSFT", "signal_fast": -0.2, "signal_slow": 0.3},
        ]
    )
    out = to_standard_signal_long_format(
        df,
        signal_cols=["signal_fast", "signal_slow"],
        signal_version="v1",
        horizon="3bars",
        source="test",
    )
    assert set(REQUIRED_SIGNAL_COLUMNS).issubset(set(out.columns))
    assert len(out) == 4


def test_validate_standard_signal_schema_deduplicates():
    df = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-02 10:00:00",
                "asset": "AAPL",
                "signal_value": 1.0,
                "signal_name": "alpha",
                "signal_version": "v1",
                "horizon": "3bars",
                "source": "test",
            },
            {
                "timestamp": "2026-01-02 10:00:00",
                "asset": "AAPL",
                "signal_value": 3.0,
                "signal_name": "alpha",
                "signal_version": "v1",
                "horizon": "3bars",
                "source": "test",
            },
        ]
    )
    out = validate_standard_signal_schema(df)
    assert len(out) == 1
    assert out.loc[0, "signal_value"] == 2.0
