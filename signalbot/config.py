import copy
import os

import yaml

TF_TO_INTERVAL = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "8h": "Hour8",
    "1d": "Day1",
    "1w": "Week1",
}

DEFAULTS = {
    "symbols": ["BTC_USDT", "ETH_USDT"],
    "higher_tf": "4h",
    "middle_tf": "1h",
    "lower_tf": "15m",
    "ema_fast": 21,
    "ema_mid": 55,
    "ema_slow": 100,
    "ema_trend": 200,
    "swing_strength": 2,
    "slope_lookback": 3,
    "pullback_lookback": 5,
    "swing_lookback": 10,
    "tolerance": 0.001,
    "min_htf_separation_pct": 0.0,
    "min_mtf_separation_pct": 0.0,
    "min_slope_pct": 0.0,
    "rejection_ratio": 2.0,
    "rr_default": 2.0,
    "min_rr": 1.5,
    "max_stop_pct": 0.05,
    "balance": 1000.0,
    "risk_pct": 0.01,
    "kline_limit": 400,
    "min_candles": 250,  # warmup guard: need enough history for EMA200 etc.
    # ATR-based stops
    "atr_period": 14,
    "stop_mode": "swing_atr",   # "swing" | "atr" | "swing_atr"
    "atr_mult": 2.0,            # used when stop_mode == "atr"
    "atr_buffer_mult": 0.5,     # used when stop_mode == "swing_atr"
    # RSI entry filter
    "rsi_enabled": True,
    "rsi_period": 14,
    "rsi_overbought": 70.0,
    "rsi_oversold": 30.0,
    "triggers": {
        "close_back_ema21": True,
        "engulfing": True,
        "rejection": True,
        "break_structure": True,
        "hl_then_hh": True,
    },
}

_TF_KEYS = ("higher_tf", "middle_tf", "lower_tf")


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: str | None = None) -> dict:
    override = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            override = yaml.safe_load(f) or {}
    cfg = _deep_merge(DEFAULTS, override)
    for key in _TF_KEYS:
        if cfg[key] not in TF_TO_INTERVAL:
            raise ValueError(
                f"{key}={cfg[key]!r} is not a supported MEXC timeframe; "
                f"choose from {sorted(TF_TO_INTERVAL)}"
            )
    return cfg
