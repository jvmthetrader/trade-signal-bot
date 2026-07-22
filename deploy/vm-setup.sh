#!/usr/bin/env bash
# One-shot VM setup for the trade-signal bot.
# Run this ON the Oracle VM, from inside the project directory:
#     bash deploy/vm-setup.sh
# Works on Ubuntu (apt) and Oracle Linux / RHEL (dnf).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
echo ">> Project: $PROJECT_DIR"

# 1. Install Python 3 + pip using whichever package manager exists.
if command -v apt-get >/dev/null 2>&1; then
  echo ">> Installing python3/pip via apt..."
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-pip
elif command -v dnf >/dev/null 2>&1; then
  echo ">> Installing python3/pip via dnf..."
  sudo dnf install -y python3 python3-pip
else
  echo "!! No apt-get or dnf found. Install python3 and python3-pip manually, then re-run."
  exit 1
fi

# 2. Install Python dependencies for the current user.
echo ">> Installing Python requirements..."
python3 -m pip install --user -r requirements.txt

# 3. Create logs dir and a private .env from the template (first run only).
mkdir -p logs
if [ ! -f deploy/.env ]; then
  cp deploy/.env.example deploy/.env
  echo ">> Created deploy/.env — EDIT IT with your Telegram token + chat id."
fi
chmod 600 deploy/.env
chmod +x deploy/run.sh deploy/vm-setup.sh

# 4. Install/refresh the cron job (every 15 minutes), de-duplicating our line.
CRON_LINE="*/15 * * * * $PROJECT_DIR/deploy/run.sh"
( crontab -l 2>/dev/null | grep -v "deploy/run.sh" || true; echo "$CRON_LINE" ) | crontab -
echo ">> Cron installed:"
crontab -l | grep "deploy/run.sh"

cat <<EOF

============================================================
Setup complete.

NEXT:
  1. Edit your secrets:      nano deploy/.env
  2. Test one run manually:  bash deploy/run.sh && tail -n 20 logs/bot.log
     (You should get a Telegram message only if a signal fires;
      "done: 0 alert(s) sent" in the log is normal and healthy.)
  3. Cron now runs it every 15 minutes automatically. Watch it with:
        tail -f logs/bot.log

Manage the schedule:
  crontab -l          # view
  crontab -e          # edit / remove the line
============================================================
EOF
