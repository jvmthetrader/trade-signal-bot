import time

import requests


def format_signal(signal) -> str:
    emoji = "🟢" if signal.direction == "long" else "🔴"
    htf, mtf, ltf = signal.timeframes
    lines = [
        f"{emoji} {signal.direction.upper()}  {signal.symbol}",
        f"TF: {htf} dir / {mtf} setup / {ltf} entry",
        f"Trigger: {signal.trigger}",
        f"Entry:  {signal.entry:,}",
        f"Stop:   {signal.stop:,}",
        f"Target: {signal.target:,}   R:R {signal.rr}",
        f"Risk:   {signal.risk_amount} USDT",
        f"Size:   {signal.position_size}  (notional ~{signal.notional} USDT)",
    ]
    return "\n".join(lines)


def send(text, token, chat_id, retries=3, sleep=None) -> bool:
    sleep = sleep or time.sleep
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.ok:
                return True
        except requests.RequestException:
            pass
        if attempt < retries:
            sleep(2 * attempt)
    return False
