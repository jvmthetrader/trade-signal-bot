from signalbot import telegram
from signalbot.strategy import Signal


def _sig():
    return Signal(
        symbol="BTC_USDT", direction="long", entry=64200.0, stop=63600.0,
        target=65800.0, rr=2.7, risk_amount=10.0, position_size=0.0166,
        notional=1066.0, trigger="break_structure", trigger_time=123,
        timeframes=("4h", "1h", "15m"),
    )


def test_format_signal_contains_key_fields():
    msg = telegram.format_signal(_sig())
    assert "LONG" in msg
    assert "BTC_USDT" in msg
    assert "64200" in msg.replace(",", "")
    assert "break_structure" in msg
    assert "R:R" in msg


def test_send_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    class Resp:
        def __init__(self, ok):
            self.ok = ok
            self.status_code = 200 if ok else 500

    def fake_post(url, json, timeout):
        calls["n"] += 1
        return Resp(calls["n"] >= 2)  # fail first, succeed second

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    ok = telegram.send("hi", "tok", "chat", retries=3, sleep=lambda s: None)
    assert ok is True
    assert calls["n"] == 2


def test_send_returns_false_after_all_retries(monkeypatch):
    class Resp:
        ok = False
        status_code = 500

    monkeypatch.setattr(telegram.requests, "post", lambda url, json, timeout: Resp())
    ok = telegram.send("hi", "tok", "chat", retries=2, sleep=lambda s: None)
    assert ok is False
