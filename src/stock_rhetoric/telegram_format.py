"""Render a `Report` as a compact Telegram MarkdownV2 message.

Pure functions — no Telegram or network imports — so the formatter is unit-testable
from synthetic Reports built with the `tests/conftest.py` fixtures.
"""

from __future__ import annotations

import re
from typing import Optional

from .report import Report
from .risk import RiskFlag
from .watchlist import WatchQuote


# MarkdownV2 reserved characters that must be backslash-escaped in body text.
# Per https://core.telegram.org/bots/api#markdownv2-style.
_MDV2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"
_MDV2_RE = re.compile(r"([%s])" % re.escape(_MDV2_SPECIALS))

# Sentiment glyphs — unicode arrows that don't need MDv2 escaping.
_TONE_GLYPH = {"positive": "↑", "negative": "↓", "neutral": "·"}

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

_HEADLINE_MAX = 80
_NEWS_RELIABLE_LIMIT = 5
_NEWS_SOCIAL_LIMIT = 2


def escape_mdv2(text: str) -> str:
    """Backslash-escape every MarkdownV2 reserved character in `text`."""
    if text is None:
        return ""
    return _MDV2_RE.sub(r"\\\1", str(text))


_MDV2_URL_RE = re.compile(r"([\\)])")


def escape_mdv2_url(url: str) -> str:
    """Escape characters reserved inside MDv2 link URLs: only `)` and `\\`."""
    if not url:
        return ""
    return _MDV2_URL_RE.sub(r"\\\1", str(url))


_YAHOO_QUOTE_URL = "https://finance.yahoo.com/quote/{}"


def yahoo_ticker_link(ticker: str) -> str:
    """Bold ticker wrapped in a MarkdownV2 link to the Yahoo Finance quote page."""
    return (
        f"[*{escape_mdv2(ticker)}*]"
        f"({escape_mdv2_url(_YAHOO_QUOTE_URL.format(ticker))})"
    )


def _fmt_num(v: Optional[float], spec: str = "{:.1f}") -> str:
    if v is None:
        return "n/a"
    try:
        return spec.format(v)
    except (TypeError, ValueError):
        return "n/a"


def _fmt_pct(v: Optional[float], digits: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.{digits}f}%"


def _fmt_score(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.0f}"


def _normalize_de(v: Optional[float]) -> Optional[float]:
    """yfinance reports D/E as a percentage when > 5 (matches scoring.py:192)."""
    if v is None:
        return None
    return v / 100 if v > 5 else v


def _header(report: Report) -> list[str]:
    c = report.fin.company
    p = report.fin.price
    name = escape_mdv2(c.name or c.ticker)
    line1 = f"{yahoo_ticker_link(c.ticker)} — {name}"
    sector_bits = [b for b in (c.sector, c.industry) if b]
    line2 = escape_mdv2(" · ".join(sector_bits)) if sector_bits else ""
    price_parts: list[str] = []
    if p.current is not None:
        price_parts.append(f"${_fmt_num(p.current, '{:.2f}')}")
    if p.low_52w is not None and p.high_52w is not None:
        price_parts.append(f"52w: ${_fmt_num(p.low_52w, '{:.2f}')}–${_fmt_num(p.high_52w, '{:.2f}')}")
    if p.return_1w is not None:
        price_parts.append(f"1w: {_fmt_pct(p.return_1w, 0)}")
    if p.return_1y is not None:
        price_parts.append(f"1y: {_fmt_pct(p.return_1y, 0)}")
    line3 = escape_mdv2("\n".join(price_parts)) if price_parts else ""
    return [l for l in (line1, line2, line3) if l]


def _verdict(report: Report) -> list[str]:
    n = report.narrative
    direction = escape_mdv2(n.direction or "n/a")
    confidence = escape_mdv2(n.confidence or "n/a")
    out = [f"*Verdict:* {direction} \\({confidence}\\)"]
    if n.rationale:
        out.append(escape_mdv2(n.rationale))
    return out

def _summary(report: Report) -> list[str]:
    text = report.narrative.executive_summary or ""
    if not text.strip():
        return []
    return ["*Summary*", escape_mdv2(text)]


def _bullets(label: str, items: list[str], limit: int = 3) -> list[str]:
    items = [s for s in (items or []) if s and s.strip()][:limit]
    if not items:
        return []
    return [f"*{label}*"] + [f"• {escape_mdv2(s)}" for s in items]


def _risk_flags(flags: list[RiskFlag], limit: int = 3) -> list[str]:
    if not flags:
        return []
    sorted_flags = sorted(flags, key=lambda f: _SEVERITY_RANK.get(f.severity, 9))
    top = sorted_flags[:limit]
    names = ", ".join(escape_mdv2(f.name) for f in top)
    line = f"*Risk flags \\({len(flags)}\\):* {names}"
    return [line]


def _finra_line(report: Report) -> list[str]:
    f = report.finra
    if f is None or f.fetch_error or not f.days:
        return []
    recent = f.recent_days(1)
    if not recent:
        return []
    last_pct = recent[-1].short_pct
    avg_z = f.avg_z_score()
    label = escape_mdv2(f.directional_label())
    pct_text = escape_mdv2(_fmt_pct(last_pct, 1))
    z_bit = f" \\(z\\={escape_mdv2(f'{avg_z:+.2f}')}\\)" if avg_z is not None else ""
    return [f"*FINRA short:* {label} · {pct_text}{z_bit}"]


def _metrics_block(report: Report) -> list[str]:
    s = report.fin.stats
    rows = [
        ("P/E", _fmt_num(s.pe)),
        ("Forward P/E", _fmt_num(s.forward_pe)),
        ("EV/EBITDA", _fmt_num(s.ev_ebitda)),
        ("Operating margin", _fmt_pct(s.operating_margin, 1)),
        ("ROE", _fmt_pct(s.roe, 1)),
        ("Debt/Equity", _fmt_num(_normalize_de(s.debt_to_equity), "{:.2f}")),
        ("FCF yield", _fmt_pct(s.fcf_yield, 1)),
    ]
    return ["*Metrics*"] + [f"{escape_mdv2(label)}: {escape_mdv2(value)}" for label, value in rows]


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _news_block(
    report: Report,
    *,
    reliable_limit: int = _NEWS_RELIABLE_LIMIT,
    social_limit: int = _NEWS_SOCIAL_LIMIT,
) -> list[str]:
    sb = report.sentiment
    if sb is None or not sb.items:
        return []
    tone = sb.tone_summary()
    header = (
        f"*News* \\({tone['positive']}\\+ / {tone['neutral']}\\= / "
        f"{tone['negative']}\\-, net {escape_mdv2(f'{tone['net']:+.2f}')}\\)"
    )
    lines = [header]
    for item in (*sb.reliable[:reliable_limit], *sb.social[:social_limit]):
        glyph = _TONE_GLYPH.get(item.sentiment_label, "·")
        source = escape_mdv2(item.source)
        title = escape_mdv2(_truncate(item.title, _HEADLINE_MAX))
        if item.url:
            title = f"[{title}]({escape_mdv2_url(item.url)})"
        lines.append(f"{glyph} {source} — {title}")
    return lines


def _earnings_block(report: Report) -> list[str]:
    fin = report.fin
    next_date = fin.next_earnings_date
    # earnings_records appears oldest-first in yfinance; show most-recent first.
    records = list(reversed(fin.earnings_records or []))[:4]
    if next_date is None and not records:
        return []
    lines = ["*Earnings*"]
    if next_date is not None:
        lines.append(f"Next: {escape_mdv2(next_date.isoformat())}")
    for r in records:
        q = escape_mdv2(r.quarter.isoformat()) if r.quarter else "n/a"
        est = escape_mdv2(_fmt_num(r.eps_estimate, "{:.2f}"))
        act = escape_mdv2(_fmt_num(r.eps_actual, "{:.2f}"))
        if r.surprise_pct is not None:
            surp = escape_mdv2(f"{r.surprise_pct:+.1f}%")
        else:
            surp = "n/a"
        lines.append(f"{q}: est {est} · act {act} · {surp}")
    return lines


def _footer(report: Report) -> list[str]:
    timings = report.stage_timings or {}
    total = sum(v for v in timings.values() if isinstance(v, (int, float)))
    if total <= 0:
        return []
    return [f"_built in {escape_mdv2(f'{total:.0f}')}s_"]


def _assemble(blocks: list[list[str]]) -> str:
    return "\n\n".join("\n".join(b) for b in blocks if b)


def format_report(report: Report, *, max_chars: int = 3800) -> str:
    """Render a Report into a MarkdownV2-safe string under `max_chars`.

    Order: Stock info · Summary · Metrics · Earnings · Verdict · Bullish · Bearish · News.
    Length governor shrinks/drops from the bottom-up, preserving header/summary/verdict.
    """
    header = _header(report)
    summary = _summary(report)
    metrics = _metrics_block(report)
    earnings = _earnings_block(report)
    verdict = _verdict(report)
    bullish = _bullets("Bullish", report.narrative.bullish)
    bearish = _bullets("Bearish", report.narrative.bearish)
    news = _news_block(report)
    footer = _footer(report)

    # Indices matter for the governor below.
    blocks = [header, summary, metrics, earnings, verdict, bullish, bearish, news, footer]
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Step 1: shrink news
    blocks[7] = _news_block(report, reliable_limit=3, social_limit=1)
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Step 2: drop news
    blocks[7] = []
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Step 3: trim bullets to two each
    blocks[5] = _bullets("Bullish", report.narrative.bullish, limit=2)
    blocks[6] = _bullets("Bearish", report.narrative.bearish, limit=2)
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Step 4: drop bullets entirely
    blocks[5] = []
    blocks[6] = []
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Step 5: drop earnings
    blocks[3] = []
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Step 6: drop metrics
    blocks[2] = []
    text = _assemble(blocks)
    if len(text) <= max_chars:
        return text

    # Last resort: truncate
    return text[: max_chars - 4].rstrip() + " …"


def format_error(ticker: str, exc: BaseException) -> str:
    """Render a graceful error message in MarkdownV2."""
    return (
        f"*{escape_mdv2(ticker.upper())}* — couldn't build report\n"
        f"`{escape_mdv2(type(exc).__name__)}`: {escape_mdv2(str(exc) or 'unknown error')}"
    )


def format_help() -> str:
    """Static help text in MarkdownV2."""
    return (
        "*stock\\-rhetoric bot*\n\n"
        "Send a ticker symbol \\(e\\.g\\. `AAPL`\\) and I'll reply with the report\\.\n"
        "Reports take 10–60s depending on the model and network\\.\n\n"
        "*Watchlist*\n"
        "`add AAPL` — track a ticker\n"
        "`remove AAPL` — stop tracking\n"
        "`list` — show your watchlist\n\n"
        "Daily digests post at 9:30 AM ET \\(1w change\\) and 4:30 PM ET \\(1d change\\)\\.\n\n"
        "_One request at a time per user\\._"
    )


def format_watchlist_ack(status: str, ticker: str, count: int = 0) -> str:
    """One-liner MarkdownV2 acknowledgement for add/remove operations."""
    t = escape_mdv2(ticker)
    if status == "added":
        return f"✓ Tracking *{t}* \\({count} in watchlist\\)\\."
    if status == "duplicate":
        return f"Already tracking *{t}*\\."
    if status == "invalid":
        return f"*{t}* isn't a valid ticker\\."
    if status == "removed":
        return f"✓ Stopped tracking *{t}*\\."
    if status == "not_in_list":
        return f"*{t}* isn't in your watchlist\\."
    return escape_mdv2(f"{status}: {ticker}")


def format_watchlist_list(quotes: list[WatchQuote]) -> str:
    """Bulleted MDv2 list with current prices, or empty-state hint."""
    if not quotes:
        return (
            "Your watchlist is empty\\. Use `add AAPL` to start tracking a ticker\\."
        )
    lines = ["*Watchlist*"]
    for q in quotes:
        price = escape_mdv2(f"${q.price:.2f}") if q.price is not None else "n/a"
        lines.append(f"• {yahoo_ticker_link(q.ticker)} {price}")
    return "\n".join(lines)


def _fmt_change(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:+.2f}%"


def _change_glyph(v: Optional[float]) -> str:
    if v is None:
        return "·"
    if v > 0:
        return "↑"
    if v < 0:
        return "↓"
    return "·"


def format_digest(mode: str, quotes: list[WatchQuote]) -> str:
    """mode='open' → 1w change. mode='close' → 1d change."""
    if mode == "open":
        header = "*Watchlist · market open · 1w change*"
        change_attr = "change_1w"
    else:
        header = "*Watchlist · market close · 1d change*"
        change_attr = "change_1d"

    if not quotes:
        return f"{header}\n_Your watchlist is empty\\._"

    lines = [header]
    for q in quotes:
        link = yahoo_ticker_link(q.ticker)
        if q.error and q.price is None:
            lines.append(f"· {link} — {escape_mdv2(q.error)}")
            continue
        change = getattr(q, change_attr)
        glyph = _change_glyph(change)
        price_text = (
            escape_mdv2(f"${q.price:.2f}") if q.price is not None else "n/a"
        )
        change_text = escape_mdv2(_fmt_change(change))
        if q.next_earnings is not None:
            earn_text = " · earn " + escape_mdv2(q.next_earnings.isoformat())
        else:
            earn_text = ""
        lines.append(f"{glyph} {link} {price_text} {change_text}{earn_text}")
    return "\n".join(lines)
