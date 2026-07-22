import pandas as pd
from signalbot import main
from signalbot.config import DEFAULTS


def _bull_htf():
    # Note: the LAST row (index 7) is a still-forming candle that
    # process_symbol must drop; rows 0-6 are the original closed-candle
    # fixture the assertions below are written against.
    df = pd.DataFrame({
        "time": range(8),
        "high": [10, 8, 12, 9, 14, 11, 16, 99],
        "low": [6, 5, 8, 7, 10, 9, 12, 1],
        "close": [9, 7, 11, 8, 13, 10, 15, 50],
        "open": [9, 7, 11, 8, 13, 10, 15, 50],
    })
    return df


def _mtf():
    # LAST row (index 7) is the forming candle, dropped by process_symbol.
    return pd.DataFrame({
        "time": range(8),
        "high": [20] * 8, "low": [5, 3, 6, 4, 7, 5, 8, 5],
        "close": [18] * 8, "open": [18] * 8,
    })


def _ltf():
    # LAST row (index 3) is the forming candle, dropped by process_symbol.
    return pd.DataFrame({
        "time": [1, 2, 3, 4],
        "open": [10, 10, 9.0, 10.5], "high": [11, 11, 11, 11],
        "low": [9, 8, 8.5, 10], "close": [10, 9, 10.5, 10.6],
    })


def _fake_get(symbol, tf, limit):
    """Return frames with all indicator columns pre-injected (deterministic).

    Each frame's last row is an in-progress "forming" candle (mirroring
    MEXC's real API behavior) that process_symbol must drop before use.
    """
    frames = {"4h": _bull_htf(), "1h": _mtf(), "15m": _ltf()}
    df = frames[tf].copy()
    if tf == "4h":
        df["ema100"] = [5, 5.2, 5.5, 5.8, 6.1, 6.4, 6.7, 7.0]
        df["ema200"] = [4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7]
    if tf == "1h":
        df["ema21"] = [17.9] * 8
        df["ema55"] = [17.0] * 8
    if tf == "15m":
        df["ema21"] = [10, 10, 10, 10]
        df["atr14"] = [1.0, 1.0, 1.0, 1.0]
        df["rsi14"] = [50, 55, 58, 60]   # not overbought -> RSI gate passes
    return df


# identity stubs: columns are already injected by _fake_get
_IDENTITY_DEPS = {
    "get_klines": _fake_get,
    "add_emas": lambda df, periods: df,
    "add_atr": lambda df, period: df,
    "add_rsi": lambda df, period: df,
}


def test_process_symbol_returns_signal():
    cfg = {**DEFAULTS, "swing_strength": 1, "pullback_lookback": 5,
           "tolerance": 0.2, "swing_lookback": 3, "min_rr": 0.1,
           "max_stop_pct": 0.9, "ema_slow": 100, "ema_trend": 200,
           "min_candles": 1}  # fixtures are short; only real API frames need 250+
    sig = main.process_symbol("BTC_USDT", cfg, dict(_IDENTITY_DEPS))
    assert sig is not None
    assert sig.direction == "long"


def test_run_dedupes_and_counts(tmp_path):
    cfg = {**DEFAULTS, "symbols": ["BTC_USDT"], "swing_strength": 1,
           "pullback_lookback": 5, "tolerance": 0.2, "swing_lookback": 3,
           "min_rr": 0.1, "max_stop_pct": 0.9, "min_candles": 1}
    # main.run reloads config from disk, so write these overrides to a file
    import yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "symbols": ["BTC_USDT"], "swing_strength": 1, "pullback_lookback": 5,
        "tolerance": 0.2, "swing_lookback": 3, "min_rr": 0.1,
        "max_stop_pct": 0.9, "min_candles": 1,
    }))
    sent = []
    deps = dict(_IDENTITY_DEPS)
    deps["send"] = lambda text, token, chat_id: (sent.append(text) or True)
    sp = str(tmp_path / "state.json")
    n1 = main.run(str(cfg_path), sp, "tok", "chat", deps=deps)
    n2 = main.run(str(cfg_path), sp, "tok", "chat", deps=deps)  # same candle -> deduped
    assert n1 == 1
    assert n2 == 0
    assert len(sent) == 1


def test_process_symbol_ignores_forming_candle():
    """The forming (last) 15m candle would trigger close_back_ema21; the
    last CLOSED candle must not, proving process_symbol drops the forming
    row before evaluating the strategy."""

    def _fake_get_forming(symbol, tf, limit):
        if tf == "4h":
            df = _bull_htf().copy()
            df["ema100"] = [5, 5.2, 5.5, 5.8, 6.1, 6.4, 6.7, 7.0]
            df["ema200"] = [4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7]
            return df
        if tf == "1h":
            df = _mtf().copy()
            df["ema21"] = [17.9] * 8
            df["ema55"] = [17.0] * 8
            return df
        # 15m: last CLOSED row (index 2) must NOT trigger close_back_ema21
        # (close <= ema21); the forming row (index 3, must be dropped)
        # WOULD trigger it (close > ema21, green).
        df = pd.DataFrame({
            "time": [1, 2, 3, 4],
            "open": [10, 10, 9.0, 9.0],
            "high": [11, 11, 11, 11],
            "low": [9, 8, 8.5, 8.5],
            "close": [10, 9, 9.5, 10.5],
        })
        df["ema21"] = [10, 10, 10, 10]
        df["atr14"] = [1.0, 1.0, 1.0, 1.0]
        df["rsi14"] = [50, 55, 58, 60]
        return df

    cfg = {**DEFAULTS, "swing_strength": 1, "pullback_lookback": 5,
           "tolerance": 0.2, "swing_lookback": 3, "min_rr": 0.1,
           "max_stop_pct": 0.9, "ema_slow": 100, "ema_trend": 200,
           "min_candles": 1,
           "triggers": {"close_back_ema21": True, "engulfing": False,
                        "rejection": False, "break_structure": False,
                        "hl_then_hh": False}}
    deps = dict(_IDENTITY_DEPS)
    deps["get_klines"] = _fake_get_forming
    sig = main.process_symbol("BTC_USDT", cfg, deps)
    assert sig is None


def test_process_symbol_returns_none_when_below_min_candles():
    """With the default min_candles (250) and the short test fixtures,
    process_symbol should skip the symbol rather than evaluate a warmup-
    starved indicator set."""
    cfg = {**DEFAULTS, "swing_strength": 1, "pullback_lookback": 5,
           "tolerance": 0.2, "swing_lookback": 3, "min_rr": 0.1,
           "max_stop_pct": 0.9, "ema_slow": 100, "ema_trend": 200}
    assert cfg["min_candles"] == 250  # sanity: guard is on by default
    sig = main.process_symbol("BTC_USDT", cfg, dict(_IDENTITY_DEPS))
    assert sig is None
