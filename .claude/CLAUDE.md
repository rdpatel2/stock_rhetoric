# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run the CLI
stock-rhetoric                  # interactive mode (shows top gainers if market open)
stock-rhetoric AAPL             # single-ticker report, then exit
stock-rhetoric --no-llm AAPL    # skip LLM prose
stock-rhetoric --deep AAPL      # include deep-dive paragraphs
stock-rhetoric -m qwen2.5:7b    # override current model

# Tests
pytest -q                       # all tests
pytest tests/test_scoring.py    # single file
pytest -k "test_strong"         # single test by name
```

## Architecture

The pipeline in `report.py:build()` is the backbone:

1. **`financials.py:fetch(ticker)`** — pulls all data from yfinance into a `Financials` dataclass (`CompanyInfo`, `PricePerformance`, `KeyStats`, list of `FinancialPeriod`). This is the **single source of truth** for all numeric data — no other module re-fetches.

2. **`aggregator.py:gather(ticker)`** — runs four sentiment sources in parallel with per-source timeouts: `sources/yfinance_news.py`, `sources/google_news.py`, `sources/sec_edgar.py`, `sources/reddit.py`. Returns a `SentimentBundle`. Each source produces `SourceItem` objects with `tier` ("reliable" or "social").

3. **`peers.py:build_peer_set(fin)`** — fetches the same industry peers via yfinance and computes median multiples (P/E, operating margin, etc.) for relative scoring.

4. **`trends.py:analyze(fin)`** — purely deterministic; computes YoY, 3-year CAGR, and direction for revenue, EPS, FCF, operating margin. Returns `TrendReport` with `MetricTrend` per series.

5. **`scoring.py:score(fin, trends, peers)`** — deterministic 0–100 scorecard across 7 categories (Growth, Profitability, Financial Stability, Cash Flow Health, Valuation, Shareholder Returns, Operational Efficiency). Uses `linmap`, `linmap_inverse`, and `tent` helper functions. **The LLM never writes scores.**

6. **`risk.py:detect(fin, trends, peers)`** — emits `RiskFlag` objects for specific quantitative tripwires (e.g., negative FCF, high leverage, declining margins).

7. **`llm.py:narrate(...)`** — streams tokens from a local Ollama model. Sends a compact JSON facts dict (built from pre-computed numbers) and parses the response using a lenient line-regex parser with key aliases. Falls back to JSON parsing if the model ignores the format. Saves raw output to `~/.cache/stock_rhetoric/llm_debug/` when parsing fails. `DEFAULT_MODEL` is `llama3.2:3b`; overridden by `OLLAMA_MODEL` env var or `--model` flag.

8. **`finra.py:fetch(ticker)`** — fetches FINRA RegSHO daily short-sale volume files (no auth required) for three venues: dark pool/off-exchange (`FNRAshvol*.txt`), NASDAQ, and NYSE. Runs in the initial parallel fetch stage alongside financials and sentiment. Returns `FinraData` containing `VenueDay` records, with derived properties: `avg_dark_pool_short_pct()`, `dark_pool_pct_of_total()`, `short_trend()` ("Rising"/"Stable"/"Falling"), `directional_label()` ("Bearish"/"Neutral"/"Bullish"). Short % ≥ 55% = Bearish, ≤ 45% = Bullish. Fetches last 5 trading days; on timeout or partial data sets `FinraData.fetch_error` and renders a note — report never crashes on FINRA failure.

9. **`render.py`** — consumes the assembled `Report` dataclass and renders all Rich tables/panels to the terminal. Presentation only.

10. **`cli.py`** — Typer entrypoint. Checks NYSE open/closed status via `market.py`, shows top gainers via `movers.py`, then enters the ticker prompt loop.

## Style

- **None checks:** Use truthiness (`if x:`) for Optional objects (Panel, Table, str, list). Use `is not None` only when `0` or `0.0` is a semantically distinct valid value — e.g., `Optional[float]` financial metrics where zero revenue growth or zero FCF differs meaningfully from missing data.

## Key Design Constraints

- **Financials is the single fetch point.** All downstream modules (trends, scoring, risk, llm, render) consume the `Financials` object. Don't add yfinance calls elsewhere.
- **Scores are deterministic.** The LLM only narrates pre-computed numbers, never invents or overrides them.
- **Every stage has a hard timeout.** Data sources use `per_source_timeout`, peers use 12s, LLM uses `OLLAMA_TIMEOUT_S` (default 90s). A slow stage must never block the report.
- **LLM uses streaming + plain-text format** (not JSON-mode) for speed on CPU-bound models. The parser tolerates markdown artifacts, alternate spellings, and JSON fallback via `_parse_structured`.

## Environment Variables

| Var | Default | Purpose |
|---|---|---|
| `SEC_EDGAR_UA` | — | Required by SEC EDGAR: `"stock-rhetoric you@example.com"` |
| `OLLAMA_MODEL` | `qwen2.5:1.5b` | Local Qwen model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_TIMEOUT_S` | `90` | LLM hard ceiling in seconds |
| `STOCK_RHETORIC_TODAY` | — | Override date (YYYY-MM-DD) for testing closed-market behavior |

## Testing Patterns

Tests use synthetic `Financials` fixtures defined in `tests/conftest.py` (`strong_company_financials`, `weak_company_financials`) — no live network calls. Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`. HTTP-level mocking uses `aioresponses`.
