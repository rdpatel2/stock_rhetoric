# stock-rhetoric Telegram bot — deployment options

## Option A: Fly.io + Groq API (recommended — free, no hardware needed)

**What you need:**
- Groq API key (free at [console.groq.com](https://console.groq.com) — no credit card)
- Telegram bot token from @BotFather; your numeric user ID from @userinfobot

**One-time setup (10 min):**

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh   # Linux/macOS
# or: brew install flyctl

# 2. Create a free account (no credit card required)
fly auth signup

# 3. Create the app (from repo root; accept suggested name and region)
fly launch --no-deploy

# 4. Set secrets (never committed to git)
fly secrets set \
  TELEGRAM_BOT_TOKEN="<token from BotFather>" \
  TELEGRAM_ALLOWED_USER_IDS="<your numeric id>" \
  GROQ_API_KEY="<key from console.groq.com>" \
  SEC_EDGAR_UA="stock-rhetoric you@example.com"

# 5. Deploy
fly deploy --dockerfile /deploy/Dockerfile
```

**Verify:** `fly logs` — you should see `starting long-polling loop` within seconds. Message your bot with `AAPL` from your phone.

**Operating notes:**
- **Logs:** `fly logs` (add `-i <instance-id>` for a specific machine)
- **Restart:** `fly machine restart`
- **Update:** `git push && fly deploy`
- **Free tier:** 3 shared-cpu-1x 256 MB VMs, always-on, 160 GB egress/month — plenty for a personal bot.
- **LLM speed:** Groq's hardware returns 350 tokens in ~2–5s. Total report time is ~15–30s (dominated by yfinance/FINRA fetches).

---

# Option B: Oracle Cloud Always Free deploy — stock-rhetoric Telegram bot

End-to-end runbook for hosting the bot 24/7 for $0 on Oracle's Always Free tier.

> **Note:** Oracle's Always Free ARM VMs are frequently capacity-exhausted. If you can't provision one, use Option A above.

## 1. Telegram setup (5 min)

1. In the Telegram app, message **@BotFather** → `/newbot` → pick a name and `@handle`. Save the **bot token**.
2. Message **@userinfobot** to get your numeric **user id**.

## 2. Create the VM

Oracle Cloud Console → Compute → Instances → **Create**:

- **Image**: Canonical Ubuntu 24.04 (Minimal, **aarch64**)
- **Shape**: `VM.Standard.A1.Flex` — **4 OCPU / 24 GB RAM** (whole Always-Free ARM allotment)
- **Networking**: assign a public IPv4; the default Security List already permits outbound traffic. **Do not open any inbound ports** — the bot uses long polling.
- **SSH**: upload your public key.

## 3. System setup

```bash
ssh ubuntu@<public-ip>
sudo apt update && sudo apt install -y python3.12 python3.12-venv git build-essential
```

## 4. Install Ollama + pull a model

```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl enable --now ollama
ollama pull qwen2.5:7b      # ~5 GB; fits comfortably in 24 GB and runs in seconds on 4 OCPU
```

## 5. Install the project

```bash
sudo mkdir -p /opt/stock-rhetoric && sudo chown ubuntu:ubuntu /opt/stock-rhetoric
git clone <repo-url> /opt/stock-rhetoric
cd /opt/stock-rhetoric
python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e .
```

## 6. Configure environment

Create `/opt/stock-rhetoric/.env` (and `chmod 600`):

```
TELEGRAM_BOT_TOKEN=<token from BotFather>
TELEGRAM_ALLOWED_USER_IDS=<your numeric id>
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT_S=120
SEC_EDGAR_UA=stock-rhetoric you@example.com
```

`TELEGRAM_ALLOWED_USER_IDS` is comma-separated. **An empty value rejects every message** — this is intentional fail-closed behavior.

## 7. Install the systemd unit

```bash
sudo cp deploy/stock-rhetoric-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stock-rhetoric-bot
```

## 8. Verify

```bash
sudo systemctl status stock-rhetoric-bot
journalctl -u stock-rhetoric-bot -f
```

Within a few seconds you should see `starting long-polling loop`. Message your bot with `AAPL` from your phone — expect a placeholder, then the formatted report 10–60 s later.

## Operating notes

- **Logs**: `journalctl -u stock-rhetoric-bot` (use `-f` to follow, `-n 200` for recent).
- **Restart**: `sudo systemctl restart stock-rhetoric-bot`.
- **Update**: `cd /opt/stock-rhetoric && git pull && .venv/bin/pip install -e . && sudo systemctl restart stock-rhetoric-bot`.
- **Idle reclamation**: Oracle has historically reclaimed Always Free VMs that sit idle for ~7 days. The bot's outbound long-poll keeps activity registered, but a `cron` job hitting any local endpoint also works as belt-and-suspenders.
- **Memory**: the unit caps the bot process at 4 GB. Ollama runs under its own service and gets the rest of the 24 GB; expect ~5 GB resident for the 7B model.
- **Egress quota**: 10 TB/month free. SMS-scale traffic uses < 1 GB/month.

## Security

- Never expose Ollama's port (11434) to the public internet — leave it on `localhost`.
- Allowlist is fail-closed; an empty `TELEGRAM_ALLOWED_USER_IDS` denies everyone.
- `TELEGRAM_SILENT_REJECT=1` (default) means unknown users get **no reply at all**, removing any signal that the bot exists.
- Rotate the bot token via BotFather `/revoke` if it leaks; update `.env` and `sudo systemctl restart stock-rhetoric-bot`.
