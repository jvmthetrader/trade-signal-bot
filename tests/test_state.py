from signalbot import state


def test_record_and_already_alerted():
    s = {}
    assert state.already_alerted(s, "BTC_USDT:long:15m:123") is False
    state.record(s, "BTC_USDT:long:15m:123")
    assert state.already_alerted(s, "BTC_USDT:long:15m:123") is True


def test_load_missing_returns_empty(tmp_path):
    assert state.load(str(tmp_path / "nope.json")) == {}


def test_save_then_load_roundtrip(tmp_path):
    p = str(tmp_path / "state.json")
    s = {"alerted": ["A", "B"]}
    state.save(p, s)
    assert state.load(p) == s


def test_load_corrupt_returns_empty(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    assert state.load(str(p)) == {}


def test_make_key_uses_signal_fields():
    class Fake:
        symbol = "BTC_USDT"
        direction = "long"
        timeframes = ("4h", "1h", "15m")
        trigger_time = 999
    assert state.make_key(Fake()) == "BTC_USDT:long:15m:999"
