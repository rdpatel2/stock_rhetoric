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
ollama pull llama3.2:3b  # ~2GB, fast model used by default

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

## Configuration

Environment variables (all optional except `SEC_EDGAR_UA`):

| Var | Default | Purpose |
|---|---|---|
| `SEC_EDGAR_UA` | — | Required by SEC EDGAR. Example: `stock-rhetoric you@example.com` |
| `OLLAMA_MODEL` | `llama3.2:3b` | Local Ollama model to use |
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
- `OLLAMA_TIMEOUT_S` — hard ceiling (default 90s). On timeout the report renders without
  prose rather than hanging.
- `OLLAMA_MODEL` — pick a different local model.

**If the LLM is still slow on your hardware**, try a smaller model and/or raise the timeout:

```bash
ollama pull qwen2.5:1.5b      # ~1 GB, very fast
ollama pull phi3.5:3.8b       # ~2 GB, decent quality
OLLAMA_MODEL=qwen2.5:1.5b OLLAMA_TIMEOUT_S=180 stock-rhetoric NVDA
```

On a GPU, a *larger* model (`llama3.2:8b`, `qwen2.5:7b`) is usually faster than a tiny
model on CPU — bigger models exploit GPU memory bandwidth better.

If the report renders but the prose / bullets / direction look blank, the model produced
output the parser couldn't interpret. The raw response is saved to
`~/.cache/stock_rhetoric/llm_debug/` for inspection.

## Testing

```bash
pytest -q
```

## Disclaimer

Educational use only. Not financial advice.
