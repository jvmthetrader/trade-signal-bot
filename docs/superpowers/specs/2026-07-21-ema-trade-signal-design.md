# EMA Multi-Timeframe Trade Signal Bot — Design

**Date:** 2026-07-21
**Status:** Approved (design phase)

## Purpose

A free, cloud-scheduled bot that watches a small list of MEXC USDT-M Futures
perpetuals, evaluates a multi-timeframe EMA pullback strategy, and sends a full
trade plan to Telegram when a fresh setup appears. No paid infrastructure, no
exchange API key required (price data is public).

## Decisions (locked)

| Topic | Decision |
|-------|----------|
| Market | MEXC USDT-M Futures (perpetuals), public kline API — no auth |
| Coins | Small custom list (user-provided), stored in config |
| Strategy | Multi-timeframe pullback: 4h trend filter + 15m entry |
| Confirmation | Candle closes back through EMA21 in trend direction |
| Entry timeframe | 15m (configurable) |
| Trend timeframe | 4h |
| Alert content | Direction, entry, stop, target, R:R, **position size** |
| Hosting | GitHub Actions, 15-minute cron (free) |
| Dedupe | `state.json` committed back to repo each run |
| Language | Python 3 (pandas for EMAs) |

## Signal Rules (concrete)

EMAs computed on each timeframe: **21, 55, 100, 200** (exponential, on close).

### 4h trend filter (regime)
- **Bullish regime:** `close > EMA100 > EMA200` AND EMA200 rising
  (EMA200[now] > EMA200[N candles ago], default N=3).
- **Bearish regime:** `close < EMA100 < EMA200` AND EMA200 falling.
- Otherwise: **no trade** for that symbol this cycle.

### 15m entry — LONG (short is the exact mirror)
All must hold on the **just-closed** 15m candle:
1. 4h regime is bullish.
2. `close > EMA100` and `close > EMA200` (15m).
3. `EMA21 > EMA55` (fast pair aligned up).
4. **Pullback occurred:** within the last `PULLBACK_LOOKBACK` candles (default 5),
   some candle's `low <= EMA21 * (1 + TOLERANCE)` — i.e. price dipped into the
   EMA21 zone. `TOLERANCE` default 0.001 (0.1%).
5. **Confirmation:** the just-closed candle `close > EMA21` AND `close > open`
   (green candle closing back above EMA21).

### Trade plan math
- **Entry** = confirmation candle close.
- **Stop** = lowest low of last `SWING_LOOKBACK` candles (default 10) for long
  (highest high for short).
- **Risk distance** = `abs(entry - stop)`.
- **Target** = `entry + RR * risk_distance` for long (`RR` default 2.0);
  also report the recent swing high (previous high) as a reference.
- **Risk amount** = `balance * risk_pct`.
- **Position size (units)** = `risk_amount / risk_distance`.
- **Notional** = `position_size * entry` (reported so leverage is calculated on
  full position size, per the risk-management notes).

## Components

Each is a small module with one job, independently testable.

- **`config.yaml`** — `symbols[]`, `entry_timeframe`, `trend_timeframe`,
  EMA periods, `tolerance`, `pullback_lookback`, `swing_lookback`, `rr`,
  `balance`, `risk_pct`, `ema200_slope_lookback`.
- **`mexc.py`** — `get_klines(symbol, interval, limit)` → list of OHLC candles
  from `https://contract.mexc.com/api/v1/contract/kline/{symbol}`. Handles
  interval mapping (15m→`Min15`, 4h→`Hour4`). Pure fetch + parse; raises on
  HTTP/parse failure.
- **`indicators.py`** — `ema(values, period)` → list; adds EMA columns to a
  candle frame. No I/O.
- **`strategy.py`** — `evaluate(symbol, entry_candles, trend_candles, cfg)` →
  `Signal | None`. Pure function; all rules above. No I/O, no network.
- **`telegram.py`** — `send(text)` via Bot API `sendMessage`. Retries on failure.
- **`state.py`** — `load()` / `save()` `state.json`; `already_alerted(key)` where
  key = `f"{symbol}:{direction}:{confirmation_candle_close_time}"`.
- **`main.py`** — loads config, loops symbols, fetches data, evaluates, dedupes,
  formats message, sends, updates state. One symbol's error is caught and logged;
  the run continues.
- **`.github/workflows/signal.yml`** — cron `*/15 * * * *`; sets up Python;
  runs `main.py` with secrets in env; commits `state.json` if changed.

## Data flow

```
cron (15 min)
  -> main.py
       for each symbol:
         mexc.get_klines(symbol, 4h)   ---\
         mexc.get_klines(symbol, 15m)  ----> indicators.add_emas
                                             -> strategy.evaluate -> Signal?
                                                  -> state.already_alerted? skip
                                                  -> telegram.send(plan)
                                                  -> state.record
  -> commit state.json back to repo
```

## Secrets & config inputs (user provides)

- GitHub Actions secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Config: coin list, `balance`, `risk_pct` (0.5%–1% suggested).
- A free GitHub account + repository.

## Error handling

- **MEXC fetch fails / bad data:** catch per symbol, log, continue to next.
  Never crash the whole run.
- **Not enough candles for EMA200 warmup:** skip symbol (need >= ~250 candles).
- **Telegram send fails:** retry up to 3 times with backoff; if still failing,
  log and do NOT record state (so it can alert next run).
- **State file missing/corrupt:** treat as empty state.

## Telegram message format (example)

```
🟢 LONG  BTC_USDT  (15m)
Trend: 4h bullish (EMA100>EMA200, rising)
Entry:  64,200
Stop:   63,600   (swing low)
Target: 65,400   (2.0R) | prev high 65,800
Risk:   1.0% of 1,000 = 10 USDT
Size:   0.0166 BTC  (notional ~1,066 USDT)
```

## Testing (TDD)

- **indicators:** EMA against hand-computed/known reference values.
- **strategy:** synthetic candle series — MUST fire (clean pullback+confirm),
  MUST NOT fire (no pullback / wrong regime / no confirmation close / tangled).
  Both long and short mirrors.
- **state:** dedupe returns True for a recorded key, False otherwise; survives
  round-trip save/load; tolerates missing/corrupt file.
- **mexc:** parse a captured sample response into candles (no live network in
  tests).

## Out of scope (YAGNI)

- Placing real orders / exchange trading keys.
- Backtesting engine.
- Web dashboard / database.
- More than the configured coin list.
- Sub-15-minute reactivity.
```
