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


def process_symbol(symbol, cfg, deps):
    get_klines = deps["get_klines"]
    add_emas = deps["add_emas"]
    add_atr = deps["add_atr"]
    add_rsi = deps["add_rsi"]
    limit = cfg["kline_limit"]

    htf = add_emas(get_klines(symbol, cfg["higher_tf"], limit),
                   [cfg["ema_slow"], cfg["ema_trend"]])
    mtf = add_emas(get_klines(symbol, cfg["middle_tf"], limit),
                   [cfg["ema_fast"], cfg["ema_mid"]])
    ltf = add_emas(get_klines(symbol, cfg["lower_tf"], limit),
                   [cfg["ema_fast"]])
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
        except Exception as e:  # one bad symbol never stops the run
            print(f"[warn] {symbol}: {e}", file=sys.stderr)
            continue
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
