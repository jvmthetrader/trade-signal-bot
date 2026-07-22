import pandas as pd
from signalbot import structure


def _df(highs, lows):
    return pd.DataFrame({"high": highs, "low": lows})


def test_swing_high_detects_local_peak():
    # index 2 is a peak with strength 2 (higher than 2 neighbors each side)
    df = _df([1, 2, 5, 2, 1], [0, 0, 0, 0, 0])
    assert structure.swing_high_idx(df, 2) == [2]


def test_swing_low_detects_local_trough():
    df = _df([9, 9, 9, 9, 9], [5, 4, 1, 4, 5])
    assert structure.swing_low_idx(df, 2) == [2]


def test_bullish_structure_hh_hl():
    # two rising swing highs and two rising swing lows
    highs = [3, 1, 1, 5, 1, 1, 7, 1, 1]
    lows = [2, 0, 1, 3, 1, 2, 4, 1, 0]
    df = _df(highs, lows)
    # swing highs at 0? no (needs neighbors). Use strength 1 helper checks below.
    assert structure.is_bullish_structure(df, 1) is True
    assert structure.is_bearish_structure(df, 1) is False


def test_bearish_structure_lh_ll():
    highs = [7, 1, 1, 5, 1, 1, 3, 1, 1]
    lows = [5, 2, 3, 4, 1, 2, 2, 1, 0]
    df = _df(highs, lows)
    assert structure.is_bearish_structure(df, 1) is True
    assert structure.is_bullish_structure(df, 1) is False


def test_higher_low_formed():
    highs = [9, 9, 9, 9, 9, 9]
    lows = [2, 1, 3, 2, 4, 3]  # swing lows (strength1) at idx1=1, idx3=2, ... rising
    df = _df(highs, lows)
    assert structure.higher_low_formed(df, 1) is True


def test_not_enough_swings_returns_false():
    df = _df([1, 2, 3], [1, 2, 3])
    assert structure.is_bullish_structure(df, 2) is False
