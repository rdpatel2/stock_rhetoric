# stock-rhetoric

Terminal CLI that compiles a structured, quantitative financial-health report for any
US-listed ticker — combining hard fundamentals (income statement, balance sheet, cash
flow, valuation, returns, trends, peer comparison) with sentiment from reliable +
social sources, and ending with a deterministic 0–100 health score and a buy/hold/sell
direction.

All data sources are free. Summarization runs locally via Ollama — nothing is paid
and no data leaves your machine.

## Setup

```bash
# 1. Python 3.11+ environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Ollama (local LLM) — required at runtime for prose generation
#    Install: https://ollama.com/download
ollama serve &           # start the local server
ollama pull qwen2.5:1.5b  # ~1G fast model used by default

# This model is extremely small (1.5b parameters is close to nothing)
# However, running on only a CPU will not allow for using a better, larger model


# 3. SEC EDGAR requires a descriptive User-Agent. Copy and edit:
cp .env.example .env
# then edit SEC_EDGAR_UA to include your name + email
```

## Run

```bash
stock-rhetoric
```

On launch the tool checks if the NYSE is open today. If open, it shows the top-5
gainers as lightweight snapshots; if closed, it skips straight to a ticker prompt.
Enter any US ticker (e.g. `AAPL`, `NVDA`) for the full 12-section report. Type `q`
to quit.

New to fundamental analysis? Run `stock-rhetoric --help` (or `-h`) for an
educational guide that explains what numeric thresholds make a stock worth a
closer look — growth, profitability, valuation, balance-sheet, cash-flow,
shareholder-returns, and red-flag heuristics — alongside the standard CLI usage.
No ticker is fetched; the guide is pure reference text.

## Configuration

Environment variables (all optional except `SEC_EDGAR_UA`):

| Var | Default | Purpose |
|---|---|---|
| `SEC_EDGAR_UA` | — | Required by SEC EDGAR. Example: `stock-rhetoric you@example.com` |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Local Ollama model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TIMEOUT_S` | `45` | Max seconds the LLM call may take; on timeout, the report renders without prose |
| `STOCK_RHETORIC_TODAY` | — | Override "today" (YYYY-MM-DD) for testing closed-market behavior |

## Performance

Every report prints per-stage timings (`fetch / peers / analytics / llm`) so you can see
where time is being spent. Data + scoring runs in ~3–10 seconds — the LLM is the only
slow piece on CPU.

During the LLM step the spinner shows live progress (`LLM streaming · N tokens · Xs`),
so you can confirm the model is actually producing output rather than hung. Tokens are
streamed and the response uses a plain-text delimited format (not JSON-mode), which is
substantially faster on small CPU-bound models. The model is kept resident for 30 minutes
between calls (`keep_alive=30m`), so the second ticker you analyze in a session is much
faster than the first (no model reload).

**By default**, the LLM only writes the executive summary, bullish / bearish bullets, and
the final direction. The deterministic tables (key metrics, trend analysis, scorecard,
risk flags) cover everything else.

**Flags / env vars**:

- `--no-llm` — skip prose entirely. The full quantitative report still renders.
- `--deep` — also generate the four deep-dive paragraphs (valuation / balance sheet /
  cash flow / competitive). Roughly doubles LLM time.
- `--model` / `-m` — override `OLLAMA_MODEL` for a single run.
- `--help` / `-h` — show the educational guide (no ticker fetched).
- `OLLAMA_TIMEOUT_S` — hard ceiling (default 90s). On timeout the report renders without
  prose rather than hanging.
- `OLLAMA_MODEL` — pick a different local model.

**If the LLM is still slow on your hardware**, try a smaller model and/or raise the timeout:

```bash
ollama pull qwen2.5:1.5b      # ~1 GB, very fast
ollama pull phi3.5:3.8b       # ~2 GB, decent quality
OLLAMA_MODEL=qwen2.5:1.5b OLLAMA_TIMEOUT_S=180 stock-rhetoric NVDA
```

On a GPU, a *larger* model (`llama3.1:8b`, `qwen2.5:7b`) is usually faster than a tiny
model on CPU — bigger models exploit GPU memory bandwidth better.

### Choosing a model for your hardware

The default `qwen2.5:1.5b` is intentionally tiny so the tool works on a CPU-only
laptop. If you have a discrete GPU or Apple Silicon, a 7B–14B model gives
noticeably sharper bull/bear bullets and a better-grounded direction with little
extra latency. Pull whichever model fits, then point the CLI at it:

```bash
ollama pull qwen2.5:7b
stock-rhetoric NVDA -m qwen2.5:7b
# or persist it across runs:
export OLLAMA_MODEL=qwen2.5:7b
```

Rule of thumb: a 4-bit quantized model fits in roughly `params × 0.6 GB` of VRAM
(or unified memory on Mac), and you want ~2 GB headroom for context.

**NVIDIA GPUs (4-bit quantized; everything above runs comfortably in VRAM):**

| GPU | VRAM | Suggested model | Notes |
|---|---|---|---|
| RTX 3060 12 GB | 12 GB | `qwen2.5:7b` or `llama3.1:8b` | Sweet spot for this tool; clean fit. |
| RTX 4060 Ti 16 GB | 16 GB | `qwen2.5:14b` | Bigger reasoning lift on bull/bear synthesis. |
| RTX 4070 / 4070 Super 12 GB | 12 GB | `qwen2.5:7b` or `gemma2:9b` | Faster than the 3060 at the same memory ceiling. |
| RTX 4080 / 4090 16–24 GB | 16–24 GB | `qwen2.5:14b` or `qwen2.5:32b` | Use 32B only if you also pass `--deep`; otherwise overkill for short prose. |

**Apple Silicon MacBooks (everyday configs from the last ~2 years):**

The whole "unified memory" pool is GPU-accessible, so target ~60–70% of total
RAM for the model and leave the rest for the OS, browser, and the CLI itself.

| Machine | Unified memory | Suggested model | Notes |
|---|---|---|---|
| MacBook Air M2 (2022) | 8 GB | `qwen2.5:1.5b` (default) or `llama3.2:3b` | Stay at ≤3B; bigger models page heavily and the system slows. |
| MacBook Air M3 (2024) | 16 GB | `qwen2.5:7b` or `llama3.1:8b` | Close other heavy apps; leaves ~6 GB headroom. |
| MacBook Pro 14" M3 (2023) | 18 GB | `qwen2.5:7b` or `gemma2:9b` | Comfortable; first-token latency under a second after warm-up. |
| MacBook Pro 14" M4 (2024) | 16–24 GB | `qwen2.5:14b` (24 GB models) or `qwen2.5:7b` (16 GB) | M4 GPU is meaningfully faster than M3; 14B becomes practical at 24 GB. |

If you're not sure what's installed, `ollama list` shows local models and
`ollama ps` shows which is currently resident. The first call after a model
switch pays the load cost (~5–15 s); subsequent calls reuse the same resident
model for 30 minutes (`keep_alive=30m`).

If the report renders but the prose / bullets / direction look blank, the model produced
output the parser couldn't interpret. The raw response is saved to
`~/.cache/stock_rhetoric/llm_debug/` for inspection.

## Short Sale Activity (FINRA)

Each report includes a **Short Sale Activity** panel sourced from FINRA's daily
RegSHO Consolidated NMS (CNMS) short-sale volume files. These are publicly
available — no account or API key required.

### Data source

FINRA publishes one pipe-delimited file per trading day covering all three major
venues (CBOE, NASDAQ, NYSE) in a single consolidated record:

```
https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
```

Each row contains the ticker, short volume, short-exempt volume, and total volume
for that day. The tool fetches the last **30 trading days** concurrently and
extracts only the row matching the requested ticker.

### What "short volume" means

Short volume is the number of shares sold short on that day across exchange-reported
trades. It is **not** the same as short interest (total outstanding short positions).
A high short-volume day means a large fraction of the day's traded shares were
initiated as short sales — this can reflect hedging, arbitrage, or directional
bearish bets, so context matters.

### How the signal is calculated

Rather than using a fixed threshold (e.g., "55% = bearish"), the signal is
stock-specific and adapts to each ticker's historical baseline:

1. **Baseline** — compute the mean and sample standard deviation of `short% =
   short_volume / total_volume` across all 30 fetched trading days.

2. **Z-score per day** — for each of the most recent 5 days:
   ```
   z = (day_short_pct − baseline_mean) / baseline_std
   ```

3. **Day label** — based on that day's z-score:
   - `z > +1.5σ` → **Bearish** (unusually high short selling relative to this stock's norm)
   - `z < −1.5σ` → **Bullish** (unusually low short selling)
   - otherwise → **Neutral**

4. **Overall signal** — the average z-score of the last 5 days is compared to the
   same ±1.5σ thresholds to produce the panel's headline **Signal**.

Using z-scores rather than absolute percentages means the signal accounts for
sector and stock-level differences. A 45% short-volume day is unremarkable for
a heavily-shorted small-cap but would be an extreme outlier for a mega-cap index
constituent.

### Panel output

```
30-day baseline · avg 42.3%  std 4.1%

 Date    Short %   Z-Score   Signal
 May 14   44.2%   +0.46σ    Neutral
 May 15   39.1%   −0.78σ    Neutral
 May 16   51.8%   +2.31σ    Bearish
 May 19   48.3%   +1.46σ    Neutral
 May 20   53.4%   +2.71σ    Bearish

Signal: Bearish   avg z-score: +1.23σ
```

If fewer than 10 days are retrieved (e.g., FINRA files are delayed or the ticker
is thinly listed), a note is shown alongside the signal and the z-score may be
less reliable. The report never crashes on a FINRA failure — the panel is simply
omitted if no data arrives within the 20-second timeout.

## Testing

```bash
pytest -q
```

## Disclaimer

Educational use only. Not financial advice.
