import pandas as pd
from signalbot import indicators


def test_ema_matches_manual_calc():
    # period=2 -> alpha=2/3, adjust=False, seed with first value
    s = pd.Series([1.0, 2.0, 3.0])
    out = indicators.ema(s, 2).tolist()
    assert abs(out[0] - 1.0) < 1e-9
    assert abs(out[1] - (2 / 3 * 2 + 1 / 3 * 1)) < 1e-9      # 1.6667
    assert abs(out[2] - (2 / 3 * 3 + 1 / 3 * out[1])) < 1e-9  # 2.5556


def test_add_emas_adds_named_columns():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]})
    out = indicators.add_emas(df, [2, 3])
    assert "ema2" in out.columns
    assert "ema3" in out.columns
    assert len(out) == 4
    # original untouched
    assert "ema2" not in df.columns


def test_atr_of_constant_range_equals_range():
    # every candle spans 2.0 with no gaps -> true range is always 2.0 -> ATR 2.0
    df = pd.DataFrame({
        "high": [12, 12, 12, 12, 12],
        "low": [10, 10, 10, 10, 10],
        "close": [11, 11, 11, 11, 11],
    })
    out = indicators.atr(df, 3).tolist()
    assert abs(out[-1] - 2.0) < 1e-9


def test_add_atr_adds_named_column():
    df = pd.DataFrame({"high": [2, 3], "low": [1, 2], "close": [1.5, 2.5]})
    out = indicators.add_atr(df, 2)
    assert "atr2" in out.columns
    assert "atr2" not in df.columns


def test_rsi_rising_series_near_100():
    s = pd.Series([float(i) for i in range(1, 30)])  # strictly increasing
    val = indicators.rsi(s, 14).iloc[-1]
    assert val > 99.0


def test_rsi_falling_series_near_0():
    s = pd.Series([float(i) for i in range(30, 1, -1)])  # strictly decreasing
    val = indicators.rsi(s, 14).iloc[-1]
    assert val < 1.0


def test_add_rsi_adds_named_column():
    df = pd.DataFrame({"close": [float(i) for i in range(1, 20)]})
    out = indicators.add_rsi(df, 14)
    assert "rsi14" in out.columns
    assert "rsi14" not in df.columns
