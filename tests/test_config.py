import pytest
from signalbot import config


def test_defaults_have_three_timeframes():
    d = config.DEFAULTS
    assert d["higher_tf"] == "4h"
    assert d["middle_tf"] == "1h"
    assert d["lower_tf"] == "15m"


def test_load_config_without_file_returns_defaults():
    cfg = config.load_config(None)
    assert cfg["higher_tf"] == "4h"
    assert cfg["risk_pct"] == 0.01


def test_defaults_include_atr_and_rsi_settings():
    d = config.DEFAULTS
    assert d["stop_mode"] == "swing_atr"
    assert d["atr_period"] == 14
    assert d["rsi_enabled"] is True
    assert d["rsi_overbought"] == 70.0
    assert d["rsi_oversold"] == 30.0


def test_load_config_merges_overrides(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("risk_pct: 0.005\nsymbols: [BTC_USDT]\n")
    cfg = config.load_config(str(p))
    assert cfg["risk_pct"] == 0.005
    assert cfg["symbols"] == ["BTC_USDT"]
    assert cfg["higher_tf"] == "4h"  # untouched default remains


def test_invalid_timeframe_raises(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("higher_tf: 2h\n")
    with pytest.raises(ValueError):
        config.load_config(str(p))
