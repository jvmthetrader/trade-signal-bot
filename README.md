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
