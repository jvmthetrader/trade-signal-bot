import pandas as pd
from signalbot import main
from signalbot.config import DEFAULTS


def _bull_htf():
    df = pd.DataFrame({
        "time": range(7),
        "high": [10, 8, 12, 9, 14, 11, 16],
        "low": [6, 5, 8, 7, 10, 9, 12],
        "close": [9, 7, 11, 8, 13, 10, 15],
        "open": [9, 7, 11, 8, 13, 10, 15],
    })
    return df


def _mtf():
    return pd.DataFrame({
        "time": range(7),
        "high": [20] * 7, "low": [5, 3, 6, 4, 7, 5, 8],
        "close": [18] * 7, "open": [18] * 7,
    })


def _ltf():
    return pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0], "high": [11, 11, 11],
        "low": [9, 8, 8.5], "close": [10, 9, 10.5],
    })


def _fake_get(symbol, tf, limit):
    """Return frames with all indicator columns pre-injected (deterministic)."""
    frames = {"4h": _bull_htf(), "1h": _mtf(), "15m": _ltf()}
    df = frames[tf].copy()
    if tf == "4h":
        df["ema100"] = [5, 5.2, 5.5, 5.8, 6.1, 6.4, 6.7]
        df["ema200"] = [4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6]
    if tf == "1h":
        df["ema21"] = [17.9] * 7
        df["ema55"] = [17.0] * 7
    if tf == "15m":
        df["ema21"] = [10, 10, 10]
        df["atr14"] = [1.0, 1.0, 1.0]
        df["rsi14"] = [50, 55, 58]   # not overbought -> RSI gate passes
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
           "max_stop_pct": 0.9, "ema_slow": 100, "ema_trend": 200}
    sig = main.process_symbol("BTC_USDT", cfg, dict(_IDENTITY_DEPS))
    assert sig is not None
    assert sig.direction == "long"


def test_run_dedupes_and_counts(tmp_path):
    cfg = {**DEFAULTS, "symbols": ["BTC_USDT"], "swing_strength": 1,
           "pullback_lookback": 5, "tolerance": 0.2, "swing_lookback": 3,
           "min_rr": 0.1, "max_stop_pct": 0.9}
    # main.run reloads config from disk, so write these overrides to a file
    import yaml
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "symbols": ["BTC_USDT"], "swing_strength": 1, "pullback_lookback": 5,
        "tolerance": 0.2, "swing_lookback": 3, "min_rr": 0.1,
        "max_stop_pct": 0.9,
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
