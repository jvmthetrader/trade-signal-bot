from dataclasses import dataclass

import pandas as pd

from signalbot import structure


@dataclass
class Signal:
    symbol: str
    direction: str
    entry: float
    stop: float
    target: float
    rr: float
    risk_amount: float
    position_size: float
    notional: float
    trigger: str
    trigger_time: int
    timeframes: tuple


def _col(df, prefix, period):
    return df[f"{prefix}{period}"]


def direction(htf: pd.DataFrame, cfg: dict) -> str | None:
    slow = cfg["ema_slow"]
    trend = cfg["ema_trend"]
    strength = cfg["swing_strength"]
    look = cfg["slope_lookback"]
    close = float(htf["close"].iloc[-1])
    ema_slow = float(_col(htf, "ema", slow).iloc[-1])
    ema_trend_now = float(_col(htf, "ema", trend).iloc[-1])
    if len(htf) <= look:
        return None
    ema_trend_prev = float(_col(htf, "ema", trend).iloc[-1 - look])
    rising = ema_trend_now > ema_trend_prev
    falling = ema_trend_now < ema_trend_prev

    def _flat_or_tangled() -> bool:
        # Avoid acting on a flat trend-EMA slope or a tangled slow/trend EMA
        # pair (default thresholds are 0.0, i.e. disabled).
        if close <= 0:
            return False
        slope_pct = abs(ema_trend_now - ema_trend_prev) / close
        if slope_pct < cfg["min_slope_pct"]:
            return True
        sep_pct = abs(ema_slow - ema_trend_now) / close
        if sep_pct < cfg["min_htf_separation_pct"]:
            return True
        return False

    if (
        close > ema_trend_now
        and ema_slow > ema_trend_now
        and rising
        and structure.is_bullish_structure(htf, strength)
    ):
        return None if _flat_or_tangled() else "long"
    if (
        close < ema_trend_now
        and ema_slow < ema_trend_now
        and falling
        and structure.is_bearish_structure(htf, strength)
    ):
        return None if _flat_or_tangled() else "short"
    return None


def setup(mtf: pd.DataFrame, direction: str, cfg: dict) -> bool:
    fast = cfg["ema_fast"]
    mid = cfg["ema_mid"]
    strength = cfg["swing_strength"]
    look = cfg["pullback_lookback"]
    tol = cfg["tolerance"]
    ema_fast = float(_col(mtf, "ema", fast).iloc[-1])
    ema_mid = float(_col(mtf, "ema", mid).iloc[-1])
    close = float(mtf["close"].iloc[-1])
    recent = mtf.iloc[-look:]

    if close > 0 and abs(ema_fast - ema_mid) / close < cfg["min_mtf_separation_pct"]:
        return False  # mtf EMAs tangled -> no clean setup

    if direction == "long":
        if not ema_fast > ema_mid:
            return False
        zone = max(ema_fast, ema_mid) * (1 + tol)
        pulled_back = (recent["low"] <= zone).any()
        return bool(pulled_back and structure.higher_low_formed(mtf, strength))
    else:
        if not ema_fast < ema_mid:
            return False
        zone = min(ema_fast, ema_mid) * (1 - tol)
        pulled_back = (recent["high"] >= zone).any()
        return bool(pulled_back and structure.lower_high_formed(mtf, strength))


def _is_rejection(row, direction, ratio):
    body = abs(row["close"] - row["open"])
    body = body if body > 0 else 1e-9
    rng = row["high"] - row["low"]
    if rng <= 0:
        return False
    if direction == "long":
        lower_wick = min(row["open"], row["close"]) - row["low"]
        return lower_wick >= ratio * body and row["close"] >= row["low"] + 0.66 * rng
    else:
        upper_wick = row["high"] - max(row["open"], row["close"])
        return upper_wick >= ratio * body and row["close"] <= row["high"] - 0.66 * rng


def trigger(ltf: pd.DataFrame, direction: str, cfg: dict) -> str | None:
    fast = cfg["ema_fast"]
    strength = cfg["swing_strength"]
    ratio = cfg["rejection_ratio"]
    trig = cfg["triggers"]
    last = ltf.iloc[-1]
    ema21 = float(_col(ltf, "ema", fast).iloc[-1])
    prev = ltf.iloc[-2] if len(ltf) >= 2 else None

    if direction == "long":
        if trig.get("close_back_ema21") and last["close"] > ema21 and last["close"] > last["open"]:
            return "close_back_ema21"
        if trig.get("engulfing") and prev is not None and (
            prev["close"] < prev["open"]
            and last["close"] > last["open"]
            and last["open"] <= prev["close"]
            and last["close"] >= prev["open"]
        ):
            return "engulfing"
        if trig.get("rejection") and _is_rejection(last, "long", ratio):
            return "rejection"
        if trig.get("break_structure"):
            highs = structure.swing_high_values(ltf, strength)
            if highs and last["close"] > highs[-1]:
                return "break_structure"
        if trig.get("hl_then_hh") and structure.higher_low_formed(ltf, strength) and structure.higher_high_formed(ltf, strength):
            return "hl_then_hh"
    else:
        if trig.get("close_back_ema21") and last["close"] < ema21 and last["close"] < last["open"]:
            return "close_back_ema21"
        if trig.get("engulfing") and prev is not None and (
            prev["close"] > prev["open"]
            and last["close"] < last["open"]
            and last["open"] >= prev["close"]
            and last["close"] <= prev["open"]
        ):
            return "engulfing"
        if trig.get("rejection") and _is_rejection(last, "short", ratio):
            return "rejection"
        if trig.get("break_structure"):
            lows = structure.swing_low_values(ltf, strength)
            if lows and last["close"] < lows[-1]:
                return "break_structure"
        if trig.get("hl_then_hh") and structure.lower_high_formed(ltf, strength) and structure.lower_low_formed(ltf, strength):
            return "hl_then_hh"
    return None


def _find_target(mtf, htf, direction, entry, strength):
    highs = structure.swing_high_values(mtf, strength) + structure.swing_high_values(htf, strength)
    lows = structure.swing_low_values(mtf, strength) + structure.swing_low_values(htf, strength)
    if direction == "long":
        above = [h for h in highs if h > entry]
        return min(above) if above else None
    else:
        below = [l for l in lows if l < entry]
        return max(below) if below else None


def _rsi_ok(ltf, dirn, cfg) -> bool:
    if not cfg.get("rsi_enabled"):
        return True
    rsi_val = float(ltf[f"rsi{cfg['rsi_period']}"].iloc[-1])
    if dirn == "long":
        return rsi_val < cfg["rsi_overbought"]
    return rsi_val > cfg["rsi_oversold"]


def _compute_stop(ltf, dirn, entry, cfg) -> float:
    mode = cfg["stop_mode"]
    recent = ltf.iloc[-cfg["swing_lookback"]:]
    atr_val = None
    if mode in ("atr", "swing_atr"):
        atr_val = float(ltf[f"atr{cfg['atr_period']}"].iloc[-1])
    if dirn == "long":
        swing = float(recent["low"].min())
        if mode == "swing":
            return swing
        if mode == "atr":
            return entry - cfg["atr_mult"] * atr_val
        return swing - cfg["atr_buffer_mult"] * atr_val  # swing_atr
    else:
        swing = float(recent["high"].max())
        if mode == "swing":
            return swing
        if mode == "atr":
            return entry + cfg["atr_mult"] * atr_val
        return swing + cfg["atr_buffer_mult"] * atr_val  # swing_atr


def evaluate(symbol, htf, mtf, ltf, cfg) -> Signal | None:
    dirn = direction(htf, cfg)
    if dirn is None:
        return None
    if not setup(mtf, dirn, cfg):
        return None
    fired = trigger(ltf, dirn, cfg)
    if fired is None:
        return None
    if not _rsi_ok(ltf, dirn, cfg):
        return None

    strength = cfg["swing_strength"]
    last = ltf.iloc[-1]
    entry = float(last["close"])

    stop = _compute_stop(ltf, dirn, entry, cfg)
    risk_distance = abs(entry - stop)
    if risk_distance <= 0:
        return None
    if risk_distance / entry > cfg["max_stop_pct"]:
        return None

    tgt = _find_target(mtf, htf, dirn, entry, strength)
    if tgt is None:
        if dirn == "long":
            tgt = entry + cfg["rr_default"] * risk_distance
        else:
            tgt = entry - cfg["rr_default"] * risk_distance
    rr = abs(tgt - entry) / risk_distance
    if rr < cfg["min_rr"]:
        return None

    risk_amount = cfg["balance"] * cfg["risk_pct"]
    position_size = risk_amount / risk_distance
    notional = position_size * entry
    trigger_time = int(last["time"]) if "time" in ltf.columns else 0

    return Signal(
        symbol=symbol,
        direction=dirn,
        entry=round(entry, 8),
        stop=round(stop, 8),
        target=round(float(tgt), 8),
        rr=round(rr, 2),
        risk_amount=round(risk_amount, 4),
        position_size=round(position_size, 8),
        notional=round(notional, 2),
        trigger=fired,
        trigger_time=trigger_time,
        timeframes=(cfg["higher_tf"], cfg["middle_tf"], cfg["lower_tf"]),
    )
