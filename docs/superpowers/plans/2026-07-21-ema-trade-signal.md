# EMA Three-Timeframe Trade Signal Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a free, GitHub-Actions-scheduled Python bot that reads MEXC Futures candles, evaluates a three-timeframe EMA + market-structure strategy, and sends full trade-plan alerts to Telegram without repeating them.

**Architecture:** Small, pure, independently-testable modules. `mexc.py` fetches candles → `indicators.py` adds EMA columns → `structure.py` detects swings/market-structure → `strategy.py` (pure function over pre-computed DataFrames) returns a `Signal | None` → `telegram.py` sends it → `state.py` dedupes across runs. `main.py` orchestrates; a GitHub Actions cron runs it every 15 min and commits `state.json` back.

**Tech Stack:** Python 3, pandas (EMAs/data), requests (HTTP), PyYAML (config), pytest (tests).

## Global Constraints

- Python 3 (target 3.11+; dev machine has 3.14). Invoke pip as `python -m pip`.
- No exchange API key: MEXC Futures kline endpoint is public.
- `strategy.evaluate` and everything in `structure.py`/`indicators.py` are PURE — no network, no file I/O, no clock.
- Candles are pandas DataFrames with lowercase columns: `time, open, high, low, close, volume`.
- EMAs are exponential with `adjust=False`, computed on `close`; column names are `ema{period}` (e.g. `ema21`).
- Timeframe strings allowed: `1m, 5m, 15m, 30m, 1h, 4h, 8h, 1d, 1w` — validated against the MEXC interval map; anything else is a hard error.
- Secrets come from env vars `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Never commit them.
- Package lives in `signalbot/`; tests in `tests/`; run tests with `python -m pytest`.
- TDD: failing test → run/see fail → minimal code → run/see pass → commit.

---

### Task 1: Project scaffolding, dependencies, and config loader

**Files:**
- Create: `requirements.txt`
- Create: `signalbot/__init__.py`
- Create: `signalbot/config.py`
- Create: `config.yaml`
- Create: `tests/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `signalbot.config.TF_TO_INTERVAL: dict[str, str]` — timeframe→MEXC interval.
  - `signalbot.config.DEFAULTS: dict` — all default settings.
  - `signalbot.config.load_config(path: str | None = None) -> dict` — returns
    DEFAULTS deep-merged with the YAML file (if present); validates that
    `higher_tf`, `middle_tf`, `lower_tf` are keys of `TF_TO_INTERVAL`, else raises
    `ValueError`.

- [ ] **Step 1: Write requirements.txt**

```text
pandas>=2.0
requests>=2.28
PyYAML>=6.0
pytest>=7.0
```

- [ ] **Step 2: Create empty package markers**

Create `signalbot/__init__.py` (empty) and `tests/__init__.py` (empty).

- [ ] **Step 3: Install dependencies**

Run: `python -m pip install -r requirements.txt`
Expected: installs pandas, requests, PyYAML, pytest without error.

- [ ] **Step 4: Write the failing test**

`tests/test_config.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL (module `signalbot.config` has no `DEFAULTS`/`load_config`).

- [ ] **Step 6: Write minimal implementation**

`signalbot/config.py`:
```python
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
```

- [ ] **Step 7: Write the starter config.yaml**

`config.yaml`:
```yaml
# Edit these. Symbols are MEXC Futures perpetual names (BASE_USDT).
symbols:
  - BTC_USDT
  - ETH_USDT
  - SOL_USDT

# Timeframes (MEXC-supported only): 1m 5m 15m 30m 1h 4h 8h 1d 1w
higher_tf: 4h     # direction
middle_tf: 1h     # setup
lower_tf: 15m     # entry

# Risk
balance: 1000.0   # account size in USDT used for position sizing
risk_pct: 0.01    # 0.01 = 1% risked per trade
min_rr: 1.5       # skip trades with reward:risk below this
max_stop_pct: 0.05  # skip if stop is wider than 5% of entry

# Stops (ATR = Average True Range on the entry timeframe)
stop_mode: swing_atr   # swing | atr | swing_atr
atr_period: 14
atr_mult: 2.0          # entry +/- atr_mult*ATR  (when stop_mode: atr)
atr_buffer_mult: 0.5   # swing +/- buffer*ATR    (when stop_mode: swing_atr)

# RSI entry filter (reject over-extended entries)
rsi_enabled: true
rsi_period: 14
rsi_overbought: 70
rsi_oversold: 30

# Entry triggers (any TRUE one fires a signal)
triggers:
  close_back_ema21: true
  engulfing: true
  rejection: true
  break_structure: true
  hl_then_hh: true
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 5 passed.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt signalbot/__init__.py signalbot/config.py config.yaml tests/__init__.py tests/test_config.py
git commit -m "feat: config loader with timeframe validation and defaults"
```

---

### Task 2: EMA, ATR, and RSI indicators

**Files:**
- Create: `signalbot/indicators.py`
- Test: `tests/test_indicators.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `signalbot.indicators.ema(series: pd.Series, period: int) -> pd.Series`
  - `signalbot.indicators.add_emas(df: pd.DataFrame, periods: list[int]) -> pd.DataFrame`
    — returns a copy with an `ema{p}` column per period.
  - `signalbot.indicators.atr(df: pd.DataFrame, period: int) -> pd.Series`
    — Wilder's Average True Range from `high`/`low`/`close`.
  - `signalbot.indicators.add_atr(df: pd.DataFrame, period: int) -> pd.DataFrame`
    — returns a copy with an `atr{period}` column.
  - `signalbot.indicators.rsi(series: pd.Series, period: int) -> pd.Series`
    — Wilder's RSI on close.
  - `signalbot.indicators.add_rsi(df: pd.DataFrame, period: int) -> pd.DataFrame`
    — returns a copy with an `rsi{period}` column.

- [ ] **Step 1: Write the failing test**

`tests/test_indicators.py`:
```python
import pandas as pd
from signalbot import indicators


def test_ema_matches_manual_calc():
    # period=2 -> alpha=2/3, adjust=False, seed with first value
    s = pd.Series([1.0, 2.0, 3.0])
    out = indicators.ema(s, 2).tolist()
    assert abs(out[0] - 1.0) < 1e-9
    assert abs(out[1] - (2 / 3 * 2 + 1 / 3 * 1)) < 1e-9      # 1.6667
    assert abs(out[2] - (2 / 3 * 3 + 1 / 3 * out[1])) < 1e-9  # 2.5556


def test_add_emas_adds_named_columns():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0]})
    out = indicators.add_emas(df, [2, 3])
    assert "ema2" in out.columns
    assert "ema3" in out.columns
    assert len(out) == 4
    # original untouched
    assert "ema2" not in df.columns


def test_atr_of_constant_range_equals_range():
    # every candle spans 2.0 with no gaps -> true range is always 2.0 -> ATR 2.0
    df = pd.DataFrame({
        "high": [12, 12, 12, 12, 12],
        "low": [10, 10, 10, 10, 10],
        "close": [11, 11, 11, 11, 11],
    })
    out = indicators.atr(df, 3).tolist()
    assert abs(out[-1] - 2.0) < 1e-9


def test_add_atr_adds_named_column():
    df = pd.DataFrame({"high": [2, 3], "low": [1, 2], "close": [1.5, 2.5]})
    out = indicators.add_atr(df, 2)
    assert "atr2" in out.columns
    assert "atr2" not in df.columns


def test_rsi_rising_series_near_100():
    s = pd.Series([float(i) for i in range(1, 30)])  # strictly increasing
    val = indicators.rsi(s, 14).iloc[-1]
    assert val > 99.0


def test_rsi_falling_series_near_0():
    s = pd.Series([float(i) for i in range(30, 1, -1)])  # strictly decreasing
    val = indicators.rsi(s, 14).iloc[-1]
    assert val < 1.0


def test_add_rsi_adds_named_column():
    df = pd.DataFrame({"close": [float(i) for i in range(1, 20)]})
    out = indicators.add_rsi(df, 14)
    assert "rsi14" in out.columns
    assert "rsi14" not in df.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: FAIL (`signalbot.indicators` missing).

- [ ] **Step 3: Write minimal implementation**

`signalbot/indicators.py`:
```python
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def add_emas(df: pd.DataFrame, periods: list[int]) -> pd.DataFrame:
    out = df.copy()
    for p in periods:
        out[f"ema{p}"] = ema(out["close"], p)
    return out


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    # Wilder's smoothing == EWM with alpha = 1/period
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def add_atr(df: pd.DataFrame, period: int) -> pd.DataFrame:
    out = df.copy()
    out[f"atr{period}"] = atr(out, period)
    return out


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # no losses at all -> rs is inf -> RSI 100 (avoid NaN from divide-by-zero)
    out = out.where(avg_loss != 0, 100.0)
    return out.astype(float)


def add_rsi(df: pd.DataFrame, period: int) -> pd.DataFrame:
    out = df.copy()
    out[f"rsi{period}"] = rsi(out["close"], period)
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add signalbot/indicators.py tests/test_indicators.py
git commit -m "feat: EMA, ATR, and RSI indicator helpers"
```

---

### Task 3: Market structure (swing detection + predicates)

**Files:**
- Create: `signalbot/structure.py`
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: nothing.
- Produces (all take a DataFrame with `high`/`low` columns and int `strength`):
  - `swing_high_idx(df, strength) -> list[int]`
  - `swing_low_idx(df, strength) -> list[int]`
  - `swing_high_values(df, strength) -> list[float]` (chronological)
  - `swing_low_values(df, strength) -> list[float]` (chronological)
  - `is_bullish_structure(df, strength) -> bool` (HH + HL)
  - `is_bearish_structure(df, strength) -> bool` (LH + LL)
  - `higher_low_formed(df, strength) -> bool`
  - `lower_high_formed(df, strength) -> bool`
  - `higher_high_formed(df, strength) -> bool`
  - `lower_low_formed(df, strength) -> bool`

- [ ] **Step 1: Write the failing test**

`tests/test_structure.py`:
```python
import pandas as pd
from signalbot import structure


def _df(highs, lows):
    return pd.DataFrame({"high": highs, "low": lows})


def test_swing_high_detects_local_peak():
    # index 2 is a peak with strength 2 (higher than 2 neighbors each side)
    df = _df([1, 2, 5, 2, 1], [0, 0, 0, 0, 0])
    assert structure.swing_high_idx(df, 2) == [2]


def test_swing_low_detects_local_trough():
    df = _df([9, 9, 9, 9, 9], [5, 4, 1, 4, 5])
    assert structure.swing_low_idx(df, 2) == [2]


def test_bullish_structure_hh_hl():
    # two rising swing highs and two rising swing lows
    highs = [3, 1, 1, 5, 1, 1, 7, 1, 1]
    lows = [1, 0, 0, 2, 0, 0, 4, 0, 0]
    df = _df(highs, lows)
    # swing highs at 0? no (needs neighbors). Use strength 1 helper checks below.
    assert structure.is_bullish_structure(df, 1) is True
    assert structure.is_bearish_structure(df, 1) is False


def test_bearish_structure_lh_ll():
    highs = [7, 1, 1, 5, 1, 1, 3, 1, 1]
    lows = [5, 0, 0, 3, 0, 0, 1, 0, 0]
    df = _df(highs, lows)
    assert structure.is_bearish_structure(df, 1) is True
    assert structure.is_bullish_structure(df, 1) is False


def test_higher_low_formed():
    highs = [9, 9, 9, 9, 9, 9]
    lows = [2, 1, 3, 2, 4, 3]  # swing lows (strength1) at idx1=1, idx3=2, ... rising
    df = _df(highs, lows)
    assert structure.higher_low_formed(df, 1) is True


def test_not_enough_swings_returns_false():
    df = _df([1, 2, 3], [1, 2, 3])
    assert structure.is_bullish_structure(df, 2) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_structure.py -v`
Expected: FAIL (`signalbot.structure` missing).

- [ ] **Step 3: Write minimal implementation**

`signalbot/structure.py`:
```python
import pandas as pd


def swing_high_idx(df: pd.DataFrame, strength: int) -> list[int]:
    highs = df["high"].tolist()
    n = len(highs)
    out = []
    for i in range(strength, n - strength):
        left = highs[i - strength:i]
        right = highs[i + 1:i + 1 + strength]
        if all(highs[i] > h for h in left) and all(highs[i] > h for h in right):
            out.append(i)
    return out


def swing_low_idx(df: pd.DataFrame, strength: int) -> list[int]:
    lows = df["low"].tolist()
    n = len(lows)
    out = []
    for i in range(strength, n - strength):
        left = lows[i - strength:i]
        right = lows[i + 1:i + 1 + strength]
        if all(lows[i] < l for l in left) and all(lows[i] < l for l in right):
            out.append(i)
    return out


def swing_high_values(df: pd.DataFrame, strength: int) -> list[float]:
    return [float(df["high"].iloc[i]) for i in swing_high_idx(df, strength)]


def swing_low_values(df: pd.DataFrame, strength: int) -> list[float]:
    return [float(df["low"].iloc[i]) for i in swing_low_idx(df, strength)]


def is_bullish_structure(df: pd.DataFrame, strength: int) -> bool:
    return higher_high_formed(df, strength) and higher_low_formed(df, strength)


def is_bearish_structure(df: pd.DataFrame, strength: int) -> bool:
    return lower_high_formed(df, strength) and lower_low_formed(df, strength)


def higher_high_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_high_values(df, strength)
    return len(v) >= 2 and v[-1] > v[-2]


def lower_high_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_high_values(df, strength)
    return len(v) >= 2 and v[-1] < v[-2]


def higher_low_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_low_values(df, strength)
    return len(v) >= 2 and v[-1] > v[-2]


def lower_low_formed(df: pd.DataFrame, strength: int) -> bool:
    v = swing_low_values(df, strength)
    return len(v) >= 2 and v[-1] < v[-2]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_structure.py -v`
Expected: 6 passed. (If a fixture's expected swing set needs tweaking, adjust the
test data — not the detection logic — until the local-peak definition is
satisfied.)

- [ ] **Step 5: Commit**

```bash
git add signalbot/structure.py tests/test_structure.py
git commit -m "feat: swing-point market-structure detection"
```

---

### Task 4: MEXC kline fetch + parse

**Files:**
- Create: `signalbot/mexc.py`
- Create: `tests/fixtures/mexc_sample.json`
- Test: `tests/test_mexc.py`

**Interfaces:**
- Consumes: `signalbot.config.TF_TO_INTERVAL`.
- Produces:
  - `signalbot.mexc.parse_klines(payload: dict) -> pd.DataFrame` — columns
    `time, open, high, low, close, volume`; raises `ValueError` on
    unsuccessful/empty payloads.
  - `signalbot.mexc.get_klines(symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame`
    — HTTP GET the MEXC contract kline endpoint and return the parsed frame.

- [ ] **Step 1: Write the sample fixture**

`tests/fixtures/mexc_sample.json` (MEXC returns parallel arrays under `data`):
```json
{
  "success": true,
  "code": 0,
  "data": {
    "time": [1700000000, 1700000900, 1700001800],
    "open": [100.0, 101.0, 102.5],
    "close": [101.0, 102.5, 103.0],
    "high": [101.5, 103.0, 103.5],
    "low": [99.5, 100.8, 101.9],
    "vol": [10.0, 12.0, 9.0]
  }
}
```

- [ ] **Step 2: Write the failing test**

`tests/test_mexc.py`:
```python
import json
from pathlib import Path

import pytest
from signalbot import mexc

FIX = Path(__file__).parent / "fixtures" / "mexc_sample.json"


def test_parse_klines_builds_frame():
    payload = json.loads(FIX.read_text())
    df = mexc.parse_klines(payload)
    assert list(df.columns) == ["time", "open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["close"].iloc[-1] == 103.0
    assert df["low"].iloc[0] == 99.5


def test_parse_klines_rejects_failure_payload():
    with pytest.raises(ValueError):
        mexc.parse_klines({"success": False, "data": {}})


def test_parse_klines_rejects_empty():
    with pytest.raises(ValueError):
        mexc.parse_klines({"success": True, "data": {"time": []}})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_mexc.py -v`
Expected: FAIL (`signalbot.mexc` missing).

- [ ] **Step 4: Write minimal implementation**

`signalbot/mexc.py`:
```python
import requests
import pandas as pd

from signalbot.config import TF_TO_INTERVAL

BASE_URL = "https://contract.mexc.com/api/v1/contract/kline"


def to_interval(timeframe: str) -> str:
    if timeframe not in TF_TO_INTERVAL:
        raise ValueError(f"unsupported timeframe: {timeframe!r}")
    return TF_TO_INTERVAL[timeframe]


def parse_klines(payload: dict) -> pd.DataFrame:
    if not payload or not payload.get("success", False):
        raise ValueError(f"MEXC returned unsuccessful payload: {payload!r}")
    data = payload.get("data") or {}
    times = data.get("time") or []
    if not times:
        raise ValueError("MEXC payload contained no candles")
    df = pd.DataFrame(
        {
            "time": data["time"],
            "open": data["open"],
            "high": data["high"],
            "low": data["low"],
            "close": data["close"],
            "volume": data.get("vol", [0] * len(times)),
        }
    )
    return df.astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": float}
    )


def get_klines(symbol: str, timeframe: str, limit: int = 400) -> pd.DataFrame:
    interval = to_interval(timeframe)
    url = f"{BASE_URL}/{symbol}"
    resp = requests.get(url, params={"interval": interval}, timeout=15)
    resp.raise_for_status()
    df = parse_klines(resp.json())
    if len(df) > limit:
        df = df.iloc[-limit:].reset_index(drop=True)
    return df
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_mexc.py -v`
Expected: 3 passed.

- [ ] **Step 6: Manual live smoke check (optional but recommended)**

Run: `python -c "from signalbot import mexc; d=mexc.get_klines('BTC_USDT','4h',300); print(len(d), d.tail(1).to_dict('records'))"`
Expected: prints a count (up to 300) and one recent candle. If MEXC changes the
field names, this is where you'll catch it — fix `parse_klines` accordingly.

- [ ] **Step 7: Commit**

```bash
git add signalbot/mexc.py tests/fixtures/mexc_sample.json tests/test_mexc.py
git commit -m "feat: MEXC futures kline fetch and parse"
```

---

### Task 5: Strategy evaluation (direction, setup, trigger, trade plan)

**Files:**
- Create: `signalbot/strategy.py`
- Test: `tests/test_strategy.py`

**Interfaces:**
- Consumes: `signalbot.structure`.
- Produces:
  - `signalbot.strategy.Signal` dataclass with fields: `symbol: str`,
    `direction: str` ("long"/"short"), `entry: float`, `stop: float`,
    `target: float`, `rr: float`, `risk_amount: float`, `position_size: float`,
    `notional: float`, `trigger: str`, `trigger_time: int`,
    `timeframes: tuple[str, str, str]`.
  - `direction(htf: pd.DataFrame, cfg: dict) -> str | None` — needs `close`,
    `ema{slow}`, `ema{trend}` columns.
  - `setup(mtf: pd.DataFrame, direction: str, cfg: dict) -> bool` — needs
    `ema{fast}`, `ema{mid}`, `low`, `high` columns.
  - `trigger(ltf: pd.DataFrame, direction: str, cfg: dict) -> str | None` — needs
    `ema{fast}`, OHLC columns; returns the name of the first enabled trigger that
    fired.
  - `evaluate(symbol, htf, mtf, ltf, cfg) -> Signal | None` — DataFrames already
    carry the EMA (and ATR/RSI) columns (added by the caller).

Note: `htf` must have `ema{ema_slow}` and `ema{ema_trend}`; `mtf` must have
`ema{ema_fast}` and `ema{ema_mid}`; `ltf` must have `ema{ema_fast}`, plus
`atr{atr_period}` when `stop_mode` uses ATR, and `rsi{rsi_period}` when
`rsi_enabled`. The caller (`main.py`) adds all of these.

- [ ] **Step 1: Write the failing test**

`tests/test_strategy.py`:
```python
import pandas as pd
from signalbot import strategy
from signalbot.config import DEFAULTS


def cfg(**over):
    c = {**DEFAULTS}
    c.update(over)
    return c


def _htf_bull():
    # rising EMAs, price above both, HH+HL structure (strength 1)
    highs = [10, 8, 12, 9, 14, 11, 16]
    lows = [6, 5, 8, 7, 10, 9, 12]
    close = [9, 7, 11, 8, 13, 10, 15]
    df = pd.DataFrame({"high": highs, "low": lows, "close": close,
                       "open": close})
    df["ema100"] = [5, 5.2, 5.5, 5.8, 6.1, 6.4, 6.7]
    df["ema200"] = [4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6]  # rising, below ema100
    return df


def test_direction_long_when_bullish(_c=None):
    c = cfg(ema_slow=100, ema_trend=200, swing_strength=1, slope_lookback=3)
    assert strategy.direction(_htf_bull(), c) == "long"


def test_direction_none_when_price_below_trend():
    df = _htf_bull()
    df.loc[df.index[-1], "close"] = 1.0  # below ema200
    c = cfg(swing_strength=1)
    assert strategy.direction(df, c) is None


def test_setup_long_true_with_pullback_and_higher_low():
    # ema21>ema55, last lows dip into ema zone, higher lows forming
    lows = [5, 3, 6, 4, 7, 5, 8]     # swing lows rising (HL)
    highs = [9, 9, 9, 9, 9, 9, 9]
    df = pd.DataFrame({"high": highs, "low": lows,
                       "close": [8] * 7, "open": [8] * 7})
    df["ema21"] = [7.9] * 7
    df["ema55"] = [7.0] * 7   # ema21 > ema55
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1,
            pullback_lookback=5, tolerance=0.2)
    assert strategy.setup(df, "long", c) is True


def test_trigger_close_back_ema21_long():
    df = pd.DataFrame({
        "open": [10, 10, 9.0],
        "high": [11, 11, 11],
        "low": [9, 8, 8.5],
        "close": [10, 9, 10.5],
    })
    df["ema21"] = [10, 10, 10]  # last close 10.5 > ema21 and green
    c = cfg(ema_fast=21, swing_strength=1,
            triggers={"close_back_ema21": True, "engulfing": False,
                      "rejection": False, "break_structure": False,
                      "hl_then_hh": False})
    assert strategy.trigger(df, "long", c) == "close_back_ema21"


def test_trigger_returns_none_when_all_disabled():
    df = pd.DataFrame({"open": [1], "high": [2], "low": [0], "close": [1.5],
                       "ema21": [1.0]})
    c = cfg(triggers={k: False for k in DEFAULTS["triggers"]})
    assert strategy.trigger(df, "long", c) is None


def test_evaluate_end_to_end_long_produces_signal():
    htf = _htf_bull()
    # rename ema columns to configured slow/trend
    mtf_lows = [5, 3, 6, 4, 7, 5, 8]
    mtf = pd.DataFrame({"high": [20] * 7, "low": mtf_lows,
                        "close": [18] * 7, "open": [18] * 7})
    mtf["ema21"] = [17.9] * 7
    mtf["ema55"] = [17.0] * 7
    ltf = pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0],
        "high": [11, 11, 11],
        "low": [9, 8, 8.5],
        "close": [10, 9, 10.5],
        "ema21": [10, 10, 10],
    })
    c = cfg(ema_fast=21, ema_mid=55, ema_slow=100, ema_trend=200,
            swing_strength=1, pullback_lookback=5, tolerance=0.2,
            swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
            balance=1000.0, risk_pct=0.01,
            stop_mode="swing", rsi_enabled=False)
    sig = strategy.evaluate("BTC_USDT", htf, mtf, ltf, c)
    assert sig is not None
    assert sig.direction == "long"
    assert sig.entry == 10.5
    assert sig.stop < sig.entry          # stop below entry for long
    assert sig.target > sig.entry        # target above entry
    assert sig.position_size > 0
    assert sig.trigger == "close_back_ema21"


def test_evaluate_skips_when_rr_too_low():
    htf = _htf_bull()
    mtf = pd.DataFrame({"high": [20] * 7, "low": [5, 3, 6, 4, 7, 5, 8],
                        "close": [18] * 7, "open": [18] * 7})
    mtf["ema21"] = [17.9] * 7
    mtf["ema55"] = [17.0] * 7
    ltf = pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0], "high": [11, 11, 11],
        "low": [9, 8, 8.5], "close": [10, 9, 10.5], "ema21": [10, 10, 10],
    })
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
            tolerance=0.2, swing_lookback=3, min_rr=99.0, max_stop_pct=0.9,
            stop_mode="swing", rsi_enabled=False)
    assert strategy.evaluate("BTC_USDT", htf, mtf, ltf, c) is None


def _long_frames():
    """Bull HTF + valid MTF setup + close-back trigger LTF, for filter tests."""
    htf = _htf_bull()
    mtf = pd.DataFrame({"high": [20] * 7, "low": [5, 3, 6, 4, 7, 5, 8],
                        "close": [18] * 7, "open": [18] * 7})
    mtf["ema21"] = [17.9] * 7
    mtf["ema55"] = [17.0] * 7
    ltf = pd.DataFrame({
        "time": [1, 2, 3],
        "open": [10, 10, 9.0], "high": [11, 11, 11],
        "low": [9, 8, 8.5], "close": [10, 9, 10.5], "ema21": [10, 10, 10],
    })
    return htf, mtf, ltf


def test_atr_stop_is_wider_than_raw_swing():
    htf, mtf, ltf = _long_frames()
    ltf["atr14"] = [1.0, 1.0, 1.0]   # buffer below the swing low
    base = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
               tolerance=0.2, swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
               rsi_enabled=False)
    swing_sig = strategy.evaluate("BTC_USDT", htf, mtf, ltf,
                                  {**base, "stop_mode": "swing"})
    atr_sig = strategy.evaluate("BTC_USDT", htf, mtf, ltf,
                                {**base, "stop_mode": "swing_atr",
                                 "atr_period": 14, "atr_buffer_mult": 0.5})
    assert atr_sig.stop < swing_sig.stop   # padded further below the swing


def test_rsi_gate_blocks_overbought_long():
    htf, mtf, ltf = _long_frames()
    ltf["rsi14"] = [50, 60, 80]   # last candle overbought
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
            tolerance=0.2, swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
            stop_mode="swing", rsi_enabled=True, rsi_overbought=70)
    assert strategy.evaluate("BTC_USDT", htf, mtf, ltf, c) is None


def test_rsi_gate_allows_normal_long():
    htf, mtf, ltf = _long_frames()
    ltf["rsi14"] = [50, 55, 58]   # not overbought
    c = cfg(ema_fast=21, ema_mid=55, swing_strength=1, pullback_lookback=5,
            tolerance=0.2, swing_lookback=3, min_rr=0.1, max_stop_pct=0.9,
            stop_mode="swing", rsi_enabled=True, rsi_overbought=70)
    assert strategy.evaluate("BTC_USDT", htf, mtf, ltf, c) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strategy.py -v`
Expected: FAIL (`signalbot.strategy` missing).

- [ ] **Step 3: Write minimal implementation**

`signalbot/strategy.py`:
```python
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

    if (
        close > ema_trend_now
        and ema_slow > ema_trend_now
        and rising
        and structure.is_bullish_structure(htf, strength)
    ):
        return "long"
    if (
        close < ema_trend_now
        and ema_slow < ema_trend_now
        and falling
        and structure.is_bearish_structure(htf, strength)
    ):
        return "short"
    return None


def setup(mtf: pd.DataFrame, direction: str, cfg: dict) -> bool:
    fast = cfg["ema_fast"]
    mid = cfg["ema_mid"]
    strength = cfg["swing_strength"]
    look = cfg["pullback_lookback"]
    tol = cfg["tolerance"]
    ema_fast = float(_col(mtf, "ema", fast).iloc[-1])
    ema_mid = float(_col(mtf, "ema", mid).iloc[-1])
    recent = mtf.iloc[-look:]

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_strategy.py -v`
Expected: all passed. If a fixture doesn't produce the intended swings, adjust the
test's OHLC arrays (not the logic) so the documented structure holds.

- [ ] **Step 5: Commit**

```bash
git add signalbot/strategy.py tests/test_strategy.py
git commit -m "feat: three-timeframe strategy evaluation and trade plan"
```

---

### Task 6: State persistence (dedupe across runs)

**Files:**
- Create: `signalbot/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `signalbot.state.load(path: str) -> dict` — returns `{}` if missing/corrupt.
  - `signalbot.state.save(path: str, state: dict) -> None`
  - `signalbot.state.already_alerted(state: dict, key: str) -> bool`
  - `signalbot.state.record(state: dict, key: str) -> None`
  - `signalbot.state.make_key(signal) -> str` — accepts a `Signal`; format
    `f"{symbol}:{direction}:{lower_tf}:{trigger_time}"`.

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL (`signalbot.state` missing).

- [ ] **Step 3: Write minimal implementation**

`signalbot/state.py`:
```python
import json
import os


def load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(path: str, state: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def already_alerted(state: dict, key: str) -> bool:
    return key in set(state.get("alerted", []))


def record(state: dict, key: str) -> None:
    alerted = state.setdefault("alerted", [])
    if key not in alerted:
        alerted.append(key)


def make_key(signal) -> str:
    lower_tf = signal.timeframes[2]
    return f"{signal.symbol}:{signal.direction}:{lower_tf}:{signal.trigger_time}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_state.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add signalbot/state.py tests/test_state.py
git commit -m "feat: run-to-run alert dedupe state"
```

---

### Task 7: Telegram sender + message formatting

**Files:**
- Create: `signalbot/telegram.py`
- Test: `tests/test_telegram.py`

**Interfaces:**
- Consumes: `signalbot.strategy.Signal`.
- Produces:
  - `signalbot.telegram.format_signal(signal) -> str` — pure, returns the message.
  - `signalbot.telegram.send(text, token, chat_id, retries=3, sleep=None) -> bool`
    — POSTs to the Bot API; retries on failure; `sleep` injectable for tests
    (defaults to `time.sleep`).

- [ ] **Step 1: Write the failing test**

`tests/test_telegram.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: FAIL (`signalbot.telegram` missing).

- [ ] **Step 3: Write minimal implementation**

`signalbot/telegram.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add signalbot/telegram.py tests/test_telegram.py
git commit -m "feat: telegram message formatting and resilient send"
```

---

### Task 8: Orchestrator (main.py)

**Files:**
- Create: `signalbot/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `config`, `mexc`, `indicators`, `strategy`, `state`, `telegram`.
- Produces:
  - `signalbot.main.process_symbol(symbol, cfg, deps) -> Signal | None` — fetches
    3 timeframes via `deps["get_klines"]`, adds EMAs (all TFs) plus ATR and RSI
    (lower TF), then evaluates. `deps` (`get_klines`, `add_emas`, `add_atr`,
    `add_rsi`, `send`) is a dict of injectable functions so this is testable
    without network.
  - `signalbot.main.run(config_path, state_path, token, chat_id, deps=None) -> int`
    — loops symbols, dedupes, sends, saves state; returns count of alerts sent.
  - `signalbot.main.main()` — CLI entry reading env vars; called by `__main__`.

- [ ] **Step 1: Write the failing test**

`tests/test_main.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL (`signalbot.main` missing).

- [ ] **Step 3: Write minimal implementation**

`signalbot/main.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_main.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the FULL suite**

Run: `python -m pytest -v`
Expected: all tests across all files pass.

- [ ] **Step 6: Commit**

```bash
git add signalbot/main.py tests/test_main.py
git commit -m "feat: orchestrator wiring symbols, dedupe, and sends"
```

---

### Task 9: GitHub Actions workflow + setup README

**Files:**
- Create: `.github/workflows/signal.yml`
- Create: `state.json`
- Create: `README.md`

**Interfaces:**
- Consumes: `signalbot.main` (run as `python -m signalbot.main`).
- Produces: scheduled cloud execution + committed `state.json`.

- [ ] **Step 1: Seed an empty state file**

`state.json`:
```json
{"alerted": []}
```

- [ ] **Step 2: Write the workflow**

`.github/workflows/signal.yml`:
```yaml
name: trade-signal

on:
  schedule:
    - cron: "*/15 * * * *"   # every 15 minutes (UTC)
  workflow_dispatch: {}       # allow manual runs

permissions:
  contents: write             # needed to commit state.json back

concurrency:
  group: trade-signal
  cancel-in-progress: false

jobs:
  signal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - run: python -m pip install -r requirements.txt

      - name: Run signal bot
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python -m signalbot.main

      - name: Commit updated state
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          if ! git diff --quiet state.json; then
            git add state.json
            git commit -m "chore: update alert state [skip ci]"
            git push
          else
            echo "no state change"
          fi
```

- [ ] **Step 3: Write the setup README**

`README.md`:
```markdown
# EMA Three-Timeframe Trade Signal Bot

Watches MEXC USDT-M Futures perpetuals on three timeframes (direction / setup /
entry) and sends trade-plan alerts to Telegram. Runs free on GitHub Actions every
15 minutes.

## One-time setup

1. **Create a Telegram bot**
   - In Telegram, message **@BotFather** → `/newbot` → follow prompts → copy the
     **bot token**.
   - Message your new bot once (say "hi") so it can DM you.
   - Get your **chat id**: open
     `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and read
     `result[].message.chat.id`.

2. **Push this repo to GitHub** (a free account is fine).

3. **Add repository secrets** (Settings → Secrets and variables → Actions → New
   repository secret):
   - `TELEGRAM_BOT_TOKEN` = your bot token
   - `TELEGRAM_CHAT_ID` = your chat id

4. **Edit `config.yaml`** — set your `symbols`, `balance`, and `risk_pct`.

5. **Enable Actions** (Actions tab → enable workflows). It then runs every 15 min.
   Use **Run workflow** on the `trade-signal` action to test immediately.

## Run locally

```bash
python -m pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=xxxx
export TELEGRAM_CHAT_ID=yyyy
python -m signalbot.main
```

## Configuration

See `config.yaml`. Key knobs: `higher_tf/middle_tf/lower_tf`, `balance`,
`risk_pct`, `min_rr`, `max_stop_pct`, and the `triggers` toggles.

## Tests

```bash
python -m pytest -v
```

## Disclaimer

This is a signal/alert tool, not financial advice and not an auto-trader. It never
places orders. Always confirm on the chart and manage your own risk.
```

- [ ] **Step 4: Verify the module runs as a script (offline dry check)**

Run: `TELEGRAM_BOT_TOKEN=x TELEGRAM_CHAT_ID=y python -c "import signalbot.main"`
Expected: imports cleanly, no error.

- [ ] **Step 5: Final full-suite run**

Run: `python -m pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/signal.yml state.json README.md
git commit -m "feat: github actions schedule and setup docs"
```

---

## Self-Review Notes

- **Spec coverage:** configurable 3 TFs (Task 1), timeframe allow-list validation
  (Task 1/4), EMA + ATR + RSI indicators (Task 2), market-structure objective rules
  (Task 3), MEXC fetch (Task 4), direction/setup/five-trigger entry + RSI filter +
  ATR stops + target/R:R/max-stop filters (Task 5), dedupe state (Task 6), Telegram
  formatting/send (Task 7), orchestration with per-symbol error isolation and
  ATR/RSI column wiring (Task 8), GitHub Actions cron + state commit + BotFather
  setup (Task 9). All spec sections map to a task.
- **Type consistency:** `Signal` fields defined in Task 5 are consumed unchanged in
  Tasks 6–8; `get_klines(symbol, timeframe, limit)`, `add_emas(df, periods)`,
  `add_atr(df, period)`, `add_rsi(df, period)`,
  `evaluate(symbol, htf, mtf, ltf, cfg)`, `send(text, token, chat_id, ...)`,
  `make_key(signal)` signatures match across tasks. The `swing_atr`/`atr`/`swing`
  values of `stop_mode` and the `rsi_enabled`/`rsi_overbought`/`rsi_oversold` keys
  are consistent between config (Task 1), strategy (Task 5), and orchestration
  (Task 8).
- **Note on test fixtures:** several strategy/structure tests use hand-built OHLC
  and hand-set EMA columns to isolate logic from 250-candle EMA warmup. If a
  fixture's swings don't match the comment, adjust the fixture data, never the
  detection logic.
```
