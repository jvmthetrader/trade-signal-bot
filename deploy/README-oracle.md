# Deploy the trade-signal bot on a free Oracle Cloud VM (24/7, no GitHub)

This runs the bot on a free always-on Linux server, so your PC can be off.
State (`state.json`) and logs live on the VM. No GitHub involved.

## Overview
1. Create a free Oracle Cloud account.
2. Create an "Always Free" VM (Ubuntu).
3. Copy this project onto the VM.
4. Run `deploy/vm-setup.sh`, edit `deploy/.env`, done — cron runs it every 15 min.

---

## 1. Create the Oracle Cloud account
- Go to https://www.oracle.com/cloud/free/ → **Start for free**.
- You must provide a **credit/debit card for identity verification**. Always Free
  resources are **not charged**; leave the account on the Free tier and it stays free.
- Pick a **Home Region** close to you (you can't change it later).

## 2. Create the VM (Compute Instance)
- Console → hamburger menu → **Compute → Instances → Create instance**.
- **Image:** click *Edit* → choose **Canonical Ubuntu** (22.04 or newer).
- **Shape:** click *Edit* →
  - Best: **Ampere (Arm) VM.Standard.A1.Flex**, 1 OCPU / 6 GB — Always Free eligible.
  - If you see **"Out of capacity"**, switch to **VM.Standard.E2.1.Micro** (AMD) —
    always available and Always Free.
- **SSH keys:** choose **Generate a key pair for me** → **Download the private key**
  (a `.key` / `.pem` file). Keep it safe — it's how you log in.
- Leave networking defaults (a public IP + VCN are created). **Create**.
- When it's **Running**, copy its **Public IP address**.

## 3. Connect via SSH
From your PC terminal (Windows has built-in `ssh`). Replace the key path and IP:

    ssh -i "C:/path/to/your-private-key.key" ubuntu@YOUR_VM_PUBLIC_IP

(Username is `ubuntu` for the Ubuntu image. If you chose Oracle Linux, it's `opc`.)
If it complains the key is too open on Windows, that's usually fine to proceed;
on macOS/Linux run `chmod 600 your-private-key.key` first.

## 4. Get the project onto the VM
The repo is **public**, so just clone it directly in the SSH session — no file
copying or SSH-key juggling needed:

    git clone https://github.com/jvmthetrader/trade-signal-bot.git
    cd trade-signal-bot

(To update later: `git pull` — no re-copy needed.)

## 5. Set it up on the VM
Still in the SSH session, from inside `trade-signal-bot`:

    bash deploy/vm-setup.sh

This installs Python + dependencies and installs a cron job that runs the bot
**every 5 minutes**. Then set your secrets and test once:

    nano deploy/.env        # paste your TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, save (Ctrl+O, Enter, Ctrl+X)
    bash deploy/run.sh      # one manual run
    tail -n 20 logs/bot.log # check output ("0 alert(s) sent" is normal)

You'll get a Telegram alert only when a real signal fires. Cron keeps it running
24/7 from now on — on a precise 5-minute schedule (unlike GitHub's loose cron).

## 6. IMPORTANT — turn off GitHub Actions to avoid DOUBLE alerts
Your bot is currently also running on GitHub Actions. If you leave both on, you'll
get **every alert twice** (once from GitHub, once from the VM) and they keep
separate state. Pick ONE. To disable the GitHub one:
- GitHub repo → **Actions** tab → **trade-signal** workflow (left) → **···** menu
  (top right) → **Disable workflow**.
(You can re-enable it anytime; the VM becomes your single source of alerts.)

## 7. Edit your coin list / risk settings
    nano config.yaml        # symbols, balance, risk_pct, thresholds
Changes take effect on the next 5-minute run. No restart needed.

---

## Managing it
- **See it run live:** `tail -f logs/bot.log`
- **View schedule:** `crontab -l`
- **Change the interval:** `crontab -e` → edit the `*/5` (e.g. `*/15` for 15 min).
- **Pause/stop:** `crontab -e` and delete (or comment out) the `deploy/run.sh` line.
- **Update the code later:** `git pull` inside `trade-signal-bot` — cron keeps going.

## Security notes
- `deploy/.env` holds your Telegram token in plain text but is `chmod 600`
  (only your user can read it) and is git-ignored. Only you have SSH access to the VM.
- No exchange API key is used — the bot only reads public MEXC price data.
- Consider revoking/rotating the bot token via @BotFather since it was shared in chat.
