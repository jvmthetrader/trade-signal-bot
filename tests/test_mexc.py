import json
from pathlib import Path

import pytest
from signalbot import mexc

FIX = Path(__file__).parent / "fixtures" / "mexc_sample.json"


def test_parse_klines_builds_frame():
    payload = json.loads(FIX.read_text())
    df = mexc.parse_klines(payload)
    assert list(df.columns) == ["time", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["close"].iloc[-1] == 103.0
    assert df["low"].iloc[0] == 99.5


def test_parse_klines_rejects_failure_payload():
    with pytest.raises(ValueError):
        mexc.parse_klines({"success": False, "data": {}})


def test_parse_klines_rejects_empty():
    with pytest.raises(ValueError):
        mexc.parse_klines({"success": True, "data": {"time": []}})
