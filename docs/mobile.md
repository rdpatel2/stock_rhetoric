# Mobile / Telegram Bot

This is the user-facing reference for the Telegram surface. For hosting/runbook
details, see [`deploy/README.md`](../deploy/README.md).

## What the bot does

- **One-shot reports.** Send a ticker (`AAPL`) and the bot replies with the full
  equity research report — same numbers and narrative as the CLI.
- **Watchlist tracking.** Add tickers to a personal watchlist per user.
- **Scheduled digests.** Two daily summary messages on trading days, one at
  market open and one after market close.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather): `/newbot` → save the
   token.
2. Get your numeric Telegram user id from [@userinfobot](https://t.me/userinfobot).
3. Populate `.env`:

   ```
   TELEGRAM_BOT_TOKEN=<token from BotFather>
   TELEGRAM_ALLOWED_USER_IDS=<your numeric id>   # comma-separated for multiple users
   # Choose one LLM backend:
   GROQ_API_KEY=<key from console.groq.com>       # recommended (free, fast)
   #   or, for local Ollama:
   # OLLAMA_MODEL=qwen2.5:7b
   # OLLAMA_HOST=http://localhost:11434
   SEC_EDGAR_UA=stock-rhetoric you@example.com
   ```

4. Start the bot: `stock-rhetoric-bot` (or run as a service — see
   `deploy/README.md`).

## Commands

| Send to the bot | What it does |
|---|---|
| `AAPL` | Full report for AAPL (10–60 s). |
| `add AAPL` | Add AAPL to your watchlist. |
| `remove AAPL` / `rm AAPL` | Stop tracking AAPL. |
| `list` / `watchlist` | Show your current watchlist with live prices. |
| `/help`, `/start` | Show help text. |

Add/remove responses:

- `✓ Tracking AAPL (3 in watchlist).` — added successfully.
- `Already tracking AAPL.` — duplicate.
- `AAPL isn't a valid ticker.` — failed yfinance validation.
- `✓ Stopped tracking AAPL.` — removed.
- `AAPL isn't in your watchlist.` — nothing to remove.

The same `add` / `remove` / `list` commands also work in the CLI prompt loop.
CLI tickers are stored under a reserved `cli` key in the same JSON file.

## Scheduled digests

| Time (America/New_York) | Trigger | Content per ticker |
|---|---|---|
| 09:30 AM | Market open | Ticker · price · **1-week change** · next earnings date |
| 04:30 PM | After market close | Ticker · price · **1-day change** · next earnings date |

Both jobs:

- Skip weekends and NYSE holidays automatically (via `market.check_nyse()`).
- Run only for Telegram users who are on the allowlist *and* have a non-empty
  watchlist.
- Render with up/down glyphs (↑/↓/·) to match the report's news section.

## Storage

The watchlist lives in a single JSON file:

- Default path: `~/.cache/stock_rhetoric/watchlists.json`
- Override: set `STOCK_RHETORIC_WATCHLIST_PATH`
- Structure: `{user_id_str: ["AAPL", "MSFT", ...]}`; the CLI uses the key `"cli"`.

No database is involved. Writes are atomic (tempfile + `os.replace`).

## Waking from suspended hosts (Fly.io)

Fly.io's free tier auto-suspends idle machines. Telegram **long polling cannot
wake a suspended machine** — the poll connection is outbound from the VM, so a
sleeping VM has no listener for inbound Telegram traffic. The bot supports two
modes:

| Mode | When to use | Set |
|---|---|---|
| Long polling | Local dev, always-on hosts (Pi, Oracle) | leave `TELEGRAM_WEBHOOK_URL` unset |
| Webhook | Fly.io / any host with idle-suspend | set `TELEGRAM_WEBHOOK_URL=https://<app>.fly.dev` |

In webhook mode, Telegram POSTs each update over HTTPS to `<URL>/webhook` (path
configurable via `TELEGRAM_WEBHOOK_PATH`). Fly's proxy automatically resumes
the suspended VM on that inbound request, and the bot processes the message
normally. If the proxy can't wake the machine before its timeout, Telegram
**retries** the delivery for up to ~24 hours, so messages aren't lost.

### Crash safety

Every incoming update is written to `STOCK_RHETORIC_PENDING_DIR` (default
`~/.cache/stock_rhetoric/pending_updates`) **before** the handler runs, and the
file is deleted on success. If the bot crashes or the machine is suspended
mid-handler, the next startup notifies the affected user(s) with:

> _I was offline when your last message arrived. Please send it again if you
> still want a reply._

Stale files are removed after notification. On Fly.io the pending dir lives on
a tiny persistent volume (`/data`) so this survives machine moves.

### Webhook env vars

| Var | Default | Purpose |
|---|---|---|
| `TELEGRAM_WEBHOOK_URL` | (unset) | If set, switches `main()` to webhook mode. Must be the public HTTPS URL of the app — e.g. `https://stock-rhetoric.fly.dev`. |
| `TELEGRAM_WEBHOOK_PATH` | `/webhook` | URL path the bot listens on. |
| `TELEGRAM_WEBHOOK_PORT` | `8080` (or `PORT`) | Local port to bind. Fly maps it to 443 externally. |
| `TELEGRAM_WEBHOOK_SECRET` | (unset) | Optional shared secret; if set, Telegram includes it in a header and PTB rejects mismatches. |
| `STOCK_RHETORIC_PENDING_DIR` | `~/.cache/.../pending_updates` | Where in-flight updates are persisted. |

## Deployment

The bot runs anywhere Python 3.11+ runs. The recommended free path is **Fly.io
+ Groq API** — see `deploy/README.md` for the full runbook (and an Oracle Cloud
alternative).

## Troubleshooting

- **No response.** The allowlist is fail-closed: an empty
  `TELEGRAM_ALLOWED_USER_IDS` rejects everyone. With `TELEGRAM_SILENT_REJECT=1`
  (the default) unknown users get no reply at all — this is by design so the
  bot looks dead to strangers.
- **Digests never arrive.** Confirm the host clock is correct and you have
  `python-telegram-bot[job-queue]` installed. Check logs (`fly logs` or
  `journalctl -u stock-rhetoric-bot`) for the `scheduled watchlist digests`
  startup line, then the per-run `digest <mode> sent` / `digest <mode> skipped`
  lines.
- **`AAPL isn't a valid ticker.`** Yahoo Finance rejected the symbol — try the
  Yahoo-formatted variant (e.g. `BRK-B`, `RY.TO`).
- **MarkdownV2 send fails.** The bot transparently falls back to plain text so
  you always see *something*. The original failure is logged.
