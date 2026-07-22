import pandas as pd
from signalbot import strategy
from signalbot.config import DEFAULTS


def cfg(**over):
    c = {**DEFAULTS}
    c.update(over)
    return c


def _htf_bull():
    # rising EMAs, price above both, HH+HL structure (strength 1)
    highs = [10, 8, 12, 9, 14, 11, 16]
    lows = [6, 5, 8, 7, 10, 9, 12]
    close = [9, 7, 11, 8, 13, 10, 15]
    df = pd.DataFrame({"high": highs, "low": lows, "close": close,
                       "open": close})
    df["ema100"] = [5, 5.2, 5.5, 5.8, 6.1, 6.4, 6.7]
    df["ema200"] = [4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6]  # rising, below ema100
    return df


def test_direction_long_when_bullish(_c=None):
    c = cfg(ema_slow=100, ema_trend=200, swing_strength=1, slope_lookback=3)
    assert strategy.direction(_htf_bull(), c) == "long"


def test_direction_none_when_price_below_trend():
    df = _htf_bull()
    df.loc[df.index[-1], "close"] = 1.0  # below ema200
    c = cfg(swing_strength=1)
    assert strategy.direction(df, c) is None


def test_setup_long_true_with_pullback_and_higher_low():
    # ema21>ema55, last lows dip into ema zone, higher lows forming
    lows = [5, 3, 6, 4, 7, 5, 8]     # swing lows rising (HL)
    highs = [9, 9, 9, 9, 9, 9, 9]
    df = pd.DataFrame({"high": highs, "low": lows,
                       "close": [8] * 7, "open": [8] * 7})
    df["ema21"] = [7.9] * 7
    df["ema55"] = [7.0] * 7   # ema21 > ema55
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1,
            pullback_lookback=5, tolerance=0.2)
    assert strategy.setup(df, "long", c) is True


def test_trigger_close_back_ema21_long():
    df = pd.DataFrame({
        "open": [10, 10, 9.0],
        "high": [11, 11, 11],
        "low": [9, 8, 8.5],
        "close": [10, 9, 10.5],
    })
    df["ema21"] = [10, 10, 10]  # last close 10.5 > ema21 and green
    c = cfg(ema_fast=21, swing_strength=1,
            triggers={"close_back_ema21": True, "engulfing": False,
                      "rejection": False, "break_structure": False,
                      "hl_then_hh": False})
    assert strategy.trigger(df, "long", c) == "close_back_ema21"


def test_trigger_returns_none_when_all_disabled():
    df = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1.5],
                       "ema21": [1.0]})
    c = cfg(triggers={k: False for k in DEFAULTS["triggers"]})
    assert strategy.trigger(df, "long", c) is None


def test_evaluate_end_to_end_long_produces_signal():
    htf = _htf_bull()
    # rename ema columns to configured slow/trend
    mtf_lows = [5, 3, 6, 4, 7, 5, 8]
    mtf = pd.DataFrame({"high": [20] * 7, "low": mtf_lows,
                        "close": [18] * 7, "open": [18] * 7})
    mtf["ema21"] = [17.9] * 7
    mtf["ema55"] = [17.0] * 7
    ltf = pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0],
        "high": [11, 11, 11],
        "low": [9, 8, 8.5],
        "close": [10, 9, 10.5],
        "ema21": [10, 10, 10],
    })
    c = cfg(ema_fast=21, ema_mid=55, ema_slow=100, ema_trend=200,
            swing_strength=1, pullback_lookback=5, tolerance=0.2,
            swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
            balance=1000.0, risk_pct=0.01,
            stop_mode="swing", rsi_enabled=False)
    sig = strategy.evaluate("BTC_USDT", htf, mtf, ltf, c)
    assert sig is not None
    assert sig.direction == "long"
    assert sig.entry == 10.5
    assert sig.stop < sig.entry          # stop below entry for long
    assert sig.target > sig.entry        # target above entry
    assert sig.position_size > 0
    assert sig.trigger == "close_back_ema21"


def test_evaluate_skips_when_rr_too_low():
    htf = _htf_bull()
    mtf = pd.DataFrame({"high": [20] * 7, "low": [5, 3, 6, 4, 7, 5, 8],
                        "close": [18] * 7, "open": [18] * 7})
    mtf["ema21"] = [17.9] * 7
    mtf["ema55"] = [17.0] * 7
    ltf = pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0], "high": [11, 11, 11],
        "low": [9, 8, 8.5], "close": [10, 9, 10.5], "ema21": [10, 10, 10],
    })
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
            tolerance=0.2, swing_lookback=3, min_rr=99.0, max_stop_pct=0.9,
            stop_mode="swing", rsi_enabled=False)
    assert strategy.evaluate("BTC_USDT", htf, mtf, ltf, c) is None


def _long_frames():
    """Bull HTF + valid MTF setup + close-back trigger LTF, for filter tests."""
    htf = _htf_bull()
    mtf = pd.DataFrame({"high": [20] * 7, "low": [5, 3, 6, 4, 7, 5, 8],
                        "close": [18] * 7, "open": [18] * 7})
    mtf["ema21"] = [17.9] * 7
    mtf["ema55"] = [17.0] * 7
    ltf = pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0], "high": [11, 11, 11],
        "low": [9, 8, 8.5], "close": [10, 9, 10.5], "ema21": [10, 10, 10],
    })
    return htf, mtf, ltf


def test_atr_stop_is_wider_than_raw_swing():
    htf, mtf, ltf = _long_frames()
    ltf["atr14"] = [1.0, 1.0, 1.0]   # buffer below the swing low
    base = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
               tolerance=0.2, swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
               rsi_enabled=False)
    swing_sig = strategy.evaluate("BTC_USDT", htf, mtf, ltf,
                                  {**base, "stop_mode": "swing"})
    atr_sig = strategy.evaluate("BTC_USDT", htf, mtf, ltf,
                                {**base, "stop_mode": "swing_atr",
                                 "atr_period": 14, "atr_buffer_mult": 0.5})
    assert atr_sig.stop < swing_sig.stop   # padded further below the swing


def test_rsi_gate_blocks_overbought_long():
    htf, mtf, ltf = _long_frames()
    ltf["rsi14"] = [50, 60, 80]   # last candle overbought
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
            tolerance=0.2, swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
            stop_mode="swing", rsi_enabled=True, rsi_overbought=70)
    assert strategy.evaluate("BTC_USDT", htf, mtf, ltf, c) is None


def test_rsi_gate_allows_normal_long():
    htf, mtf, ltf = _long_frames()
    ltf["rsi14"] = [50, 55, 58]   # not overbought
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
            tolerance=0.2, swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
            stop_mode="swing", rsi_enabled=True, rsi_overbought=70)
    assert strategy.evaluate("BTC_USDT", htf, mtf, ltf, c) is not None
