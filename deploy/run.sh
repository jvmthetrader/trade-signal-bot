#!/usr/bin/env bash
# Wrapper the cron job calls every 15 minutes.
# Loads secrets from deploy/.env (never committed), then runs the bot once.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# Load TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from deploy/.env
set -a
[ -f deploy/.env ] && . deploy/.env
set +a

mkdir -p logs
# Timestamped run; stdout+stderr appended to the log.
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] run start" >> logs/bot.log
python3 -m signalbot.main >> logs/bot.log 2>&1
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] run end" >> logs/bot.log
