# EMA Three-Timeframe Trade Signal Bot — Design

**Date:** 2026-07-21
**Status:** Approved (design phase)

## Purpose

A free, cloud-scheduled bot that watches a small list of MEXC USDT-M Futures
perpetuals, evaluates a **three-timeframe** EMA + market-structure strategy, and
sends a full trade plan to Telegram when a fresh setup appears. No paid
infrastructure, no exchange API key required (price data is public).

## Decisions (locked)

| Topic | Decision |
|-------|----------|
| Market | MEXC USDT-M Futures (perpetuals), public kline API — no auth |
| Coins | Small custom list (user-provided), stored in config |
| Strategy | 3-timeframe: higher = direction, middle = setup, lower = entry |
| Timeframes | **Configurable** (`higher_tf` / `middle_tf` / `lower_tf`), default 4h / 1h / 15m |
| Entry triggers | Any of five confirmations (OR), each toggleable in config |
| Entry filter | **RSI** (Wilder, entry TF) rejects over-extended entries |
| Stops | **ATR-based** (`stop_mode`: swing / atr / swing_atr), swing_atr default |
| Alert content | Direction, entry, stop, target, R:R, **position size** |
| Hosting | GitHub Actions, 15-minute cron (free) |
| Dedupe | `state.json` committed back to repo each run |
| Language | Python 3 (pandas for EMAs) |

## Guiding principle (from user's notes)

The three timeframes need NOT show the same EMA arrangement. The higher TF sets
direction, the middle TF finds the pullback, the lower TF confirms the entry. A
temporary bearish look on the lower TF during a higher-TF uptrend is the pullback
itself — therefore **EMA alignment is NOT required on the lower timeframe**; it is
purely a price-action trigger.

## Configurable timeframes

`higher_tf`, `middle_tf`, `lower_tf` are chosen from what MEXC Futures serves:
`1m, 5m, 15m, 30m, 1h, 4h, 8h, 1d, 1w` (mapped to MEXC intervals
`Min1, Min5, Min15, Min30, Min60, Hour4, Hour8, Day1, Week1`). MEXC has no
2h/6h/12h. Config is validated against this allow-list; invalid values raise a
clear error at startup. Default: `4h / 1h / 15m`.

## Market structure (objective definitions)

Built in `structure.py` on **swing points**:
- **Swing high** = a candle whose high is strictly greater than the highs of the
  `L` candles on each side (`swing_strength L`, default 2). **Swing low** = mirror.
- **Bullish structure** = last swing-high > prior swing-high AND last swing-low >
  prior swing-low (HH + HL).
- **Bearish structure** = last swing-high < prior swing-high AND last swing-low <
  prior swing-low (LH + LL).
- **Higher low formed** = most recent swing-low > previous swing-low.
- **Lower high formed** = most recent swing-high < previous swing-high.
- **Break above structure** = close > most recent swing-high (mirror for short).

## Signal Rules (concrete)

EMAs are exponential, computed on close.

### Higher TF — direction (EMA 100, 200)
- **Bullish (long-only):** `close > EMA200` AND `EMA100 > EMA200` AND EMA200 rising
  (EMA200[now] > EMA200[now - slope_lookback], default 3) AND bullish structure.
- **Bearish (short-only):** mirror.
- **No clear direction (skip):** neither holds, OR EMA200 slope is near-flat
  (`abs(slope) < min_slope_pct` of price, default 0.0), OR EMA100/EMA200 separation
  below `min_htf_separation_pct` (tangled).

### Middle TF — setup (EMA 21, 55)
Long setup (short = mirror):
1. Higher TF is bullish.
2. `EMA21 > EMA55` (and separation ≥ `min_mtf_separation_pct` — not tangled).
3. **Pullback:** within last `pullback_lookback` candles (default 5), a low
   reached the EMA21 or EMA55 zone: `low <= max(EMA21, EMA55) * (1 + tolerance)`
   (tolerance default 0.001).
4. **Higher low formed** (most recent swing-low > previous swing-low).

### Lower TF — entry trigger (EMA 21)
Middle setup must be present. Fire on the **just-closed** candle if **any enabled**
trigger is true (all default ON, each toggleable):
1. **close_back_ema21:** `close > EMA21` and green candle (`close > open`).
2. **engulfing:** bullish engulfing (prev red, current green, current body
   engulfs prev body: `open <= prev_close` and `close >= prev_open`).
3. **rejection:** lower-wick-dominant candle — `lower_wick >= rejection_ratio *
   body` (default 2.0) and close in the upper third of the range.
4. **break_structure:** `close >` most recent swing-high on the lower TF.
5. **hl_then_hh:** a higher low followed by a higher high (two consecutive
   rising swings).
Short triggers are the exact mirrors (red candle, bearish engulfing, upper-wick
rejection, close below swing-low, LH-then-LL).

### RSI filter (entry TF) — "don't chase extremes"
After a trigger fires, an RSI gate can veto the entry (`rsi_enabled`, default on;
`rsi_period` 14, Wilder's smoothing, computed on the entry/lower TF close):
- **Long rejected** if `RSI >= rsi_overbought` (default 70).
- **Short rejected** if `RSI <= rsi_oversold` (default 30).
This reinforces the "avoid entering into over-extended price" rule without
over-filtering normal pullbacks. Set `rsi_enabled: false` to disable.

### Trade plan
- **Entry** = trigger candle close.
- **ATR** = Wilder's Average True Range over `atr_period` (default 14) on the
  lower TF.
- **Stop** depends on `stop_mode` (default `swing_atr`):
  - `swing` — lowest low of last `swing_lookback` lower-TF candles (long) /
    highest high (short). The original swing invalidation.
  - `atr` — `entry - atr_mult * ATR` (long) / `entry + atr_mult * ATR` (short),
    `atr_mult` default 2.0.
  - `swing_atr` — the swing extreme padded by `atr_buffer_mult * ATR`
    (default 0.5): `swing_low - atr_buffer_mult*ATR` (long) /
    `swing_high + atr_buffer_mult*ATR` (short). Keeps the swing basis but adds a
    volatility cushion so ordinary wicks don't trigger the stop.
- **Risk distance** = `abs(entry - stop)`.
- **Target** = nearest swing high (long) / swing low (short) on the middle or
  higher TF that is beyond entry ("previous resistance/support"); if none is
  found, fall back to `entry ± rr_default * risk_distance` (default 2.0).
- **R:R** = `abs(target - entry) / risk_distance`. If `R:R < min_rr` (default 1.5)
  → **skip** (implements "target doesn't provide enough reward").
- **Max stop width:** if `risk_distance / entry > max_stop_pct` (default 0.05)
  → **skip** ("stop too wide").
- **Risk amount** = `balance * risk_pct`. **Position size** =
  `risk_amount / risk_distance`. **Notional** = `position_size * entry` (reported
  so leverage is judged on full position size).

## Components

- **`config.yaml`** — `symbols[]`; `higher_tf`/`middle_tf`/`lower_tf`; EMA periods;
  `swing_strength`; `slope_lookback`; `pullback_lookback`; `swing_lookback`;
  tolerances/separations; `triggers{}` toggles; `rejection_ratio`; `rr_default`;
  `min_rr`; `max_stop_pct`; `balance`; `risk_pct`; `atr_period`; `stop_mode`;
  `atr_mult`; `atr_buffer_mult`; `rsi_enabled`; `rsi_period`; `rsi_overbought`;
  `rsi_oversold`.
- **`mexc.py`** — `get_klines(symbol, interval, limit)` from
  `https://contract.mexc.com/api/v1/contract/kline/{symbol}`; timeframe→interval
  mapping + validation. Pure fetch/parse; raises on failure.
- **`indicators.py`** — `ema`, `atr` (Wilder), `rsi` (Wilder), and column-adders
  (`add_emas`, `add_atr`, `add_rsi`). No I/O.
- **`structure.py`** — swing detection + the structure predicates above. No I/O.
- **`strategy.py`** — `evaluate(symbol, htf, mtf, ltf, cfg)` → `Signal | None`.
  Pure; all rules above; no network.
- **`telegram.py`** — `send(text)` via Bot API `sendMessage`; retries.
- **`state.py`** — `load`/`save` `state.json`; `already_alerted(key)`,
  key = `f"{symbol}:{direction}:{ltf}:{trigger_candle_close_time}"`.
- **`main.py`** — load config; per symbol fetch 3 timeframes, evaluate, dedupe,
  format, send, record. One symbol's error is caught + logged; run continues.
- **`.github/workflows/signal.yml`** — cron `*/15 * * * *`; setup Python; run with
  secrets in env; commit `state.json` if changed.

## Data flow

```
cron (15 min)
  -> main.py
       for each symbol:
         mexc.get_klines(symbol, higher_tf)  -> indicators + structure -> direction
         mexc.get_klines(symbol, middle_tf)  -> indicators + structure -> setup
         mexc.get_klines(symbol, lower_tf)   -> indicators + structure -> trigger
         strategy.evaluate(...) -> Signal?
              -> state.already_alerted? skip
              -> telegram.send(plan) -> state.record
  -> commit state.json back to repo
```

## Secrets & config inputs (user provides)

- GitHub Actions secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Config: coin list, `balance`, `risk_pct` (0.5%–1% suggested).
- A free GitHub account + repository.

## Error handling

- **MEXC fetch fails / bad data / too few candles for EMA200 warmup
  (need ≈250+):** catch per symbol, log, continue.
- **Telegram send fails:** retry up to 3× with backoff; if still failing, log and
  do NOT record state (retry next run).
- **State file missing/corrupt:** treat as empty.
- **Invalid config (bad timeframe, missing secret):** fail fast with clear message.

## Telegram message format (example)

```
🟢 LONG  BTC_USDT
TF: 4h dir / 1h setup / 15m entry
Trigger: break of structure + close>EMA21
Entry:  64,200
Stop:   63,450   (15m swing low − 0.5·ATR)
Target: 65,800   (prev 1h high) | R:R 2.1
Risk:   1.0% of 1,000 = 10 USDT
Size:   0.0166 BTC  (notional ~1,066 USDT)
```

## Testing (TDD)

- **indicators:** EMA vs known reference values; ATR of constant-range candles
  equals that range; RSI → ~100 for a strictly rising series, ~0 for falling.
- **structure:** synthetic series → correct swing points; HH/HL vs LH/LL;
  higher-low / break-of-structure detection.
- **strategy:** synthetic 3-TF fixtures — MUST fire (clean direction+setup+
  trigger), MUST NOT fire (no direction / no pullback / no higher low / no
  trigger / R:R too low / stop too wide / RSI over-extended). Long and short
  mirrors. Each trigger toggled independently. ATR stop is wider than the raw
  swing stop; RSI gate blocks an overbought long.
- **state:** dedupe round-trips; tolerates missing/corrupt file.
- **mexc:** parse a captured sample response (no live network in tests).

## Out of scope (YAGNI)

- Placing real orders / trading keys.
- Backtesting engine, web dashboard, database.
- More than the configured coin list.
- Sub-15-minute reactivity / timeframes MEXC doesn't serve.
```
