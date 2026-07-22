import os
import sys

from signalbot import config as config_mod
from signalbot import indicators, mexc, state, strategy, telegram


def _default_deps():
    return {
        "get_klines": mexc.get_klines,
        "add_emas": indicators.add_emas,
        "add_atr": indicators.add_atr,
        "add_rsi": indicators.add_rsi,
        "send": telegram.send,
    }


def _drop_forming_candle(df):
    """MEXC's kline frame's LAST row is the still-forming (in-progress)
    interval, not a closed candle. Acting on it risks repainting the signal
    (its values keep changing) and effectively entering intra-bar instead of
    on the just-closed candle the spec requires. Drop it before any
    indicators are computed so EMAs/ATR/RSI and the strategy only ever see
    closed candles.
    """
    return df.iloc[:-1].reset_index(drop=True) if len(df) else df


def process_symbol(symbol, cfg, deps):
    get_klines = deps["get_klines"]
    add_emas = deps["add_emas"]
    add_atr = deps["add_atr"]
    add_rsi = deps["add_rsi"]
    limit = cfg["kline_limit"]

    raw_htf = _drop_forming_candle(get_klines(symbol, cfg["higher_tf"], limit))
    raw_mtf = _drop_forming_candle(get_klines(symbol, cfg["middle_tf"], limit))
    raw_ltf = _drop_forming_candle(get_klines(symbol, cfg["lower_tf"], limit))

    min_candles = cfg["min_candles"]
    if (len(raw_htf) < min_candles
            or len(raw_mtf) < min_candles
            or len(raw_ltf) < min_candles):
        print(
            f"[warn] {symbol}: not enough closed candles for warmup "
            f"(htf={len(raw_htf)} mtf={len(raw_mtf)} ltf={len(raw_ltf)}, "
            f"need >= {min_candles}); skipping",
            file=sys.stderr,
        )
        return None

    htf = add_emas(raw_htf, [cfg["ema_slow"], cfg["ema_trend"]])
    mtf = add_emas(raw_mtf, [cfg["ema_fast"], cfg["ema_mid"]])
    ltf = add_emas(raw_ltf, [cfg["ema_fast"]])
    ltf = add_atr(ltf, cfg["atr_period"])   # for ATR-based stops
    ltf = add_rsi(ltf, cfg["rsi_period"])   # for the RSI entry filter
    return strategy.evaluate(symbol, htf, mtf, ltf, cfg)


def run(config_path, state_path, token, chat_id, deps=None) -> int:
    deps = deps or _default_deps()
    cfg = config_mod.load_config(config_path)
    st = state.load(state_path)
    sent = 0
    for symbol in cfg["symbols"]:
        try:
            sig = process_symbol(symbol, cfg, deps)
            if sig is None:
                continue
            key = state.make_key(sig)
            if state.already_alerted(st, key):
                continue
            msg = telegram.format_signal(sig)
            if deps["send"](msg, token, chat_id):
                state.record(st, key)
                sent += 1
                print(f"[alert] {key}")
            else:
                print(f"[warn] telegram send failed for {key}", file=sys.stderr)
        except Exception as e:  # one bad symbol never stops the run
            print(f"[warn] {symbol}: {e}", file=sys.stderr)
            continue
    state.save(state_path, st)
    return sent


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("ERROR: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID", file=sys.stderr)
        sys.exit(1)
    n = run("config.yaml", "state.json", token, chat_id)
    print(f"done: {n} alert(s) sent")


if __name__ == "__main__":
    main()
