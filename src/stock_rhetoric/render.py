"""Terminal rendering of the 12-section report via `rich`."""

from __future__ import annotations

from datetime import date as _date
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .financials import Financials
from .movers import MoverSnapshot
from .report import Report
from .scoring import Scorecard

DISCLAIMER = "Educational use only. Not financial advice."


# --------------------------------------------------------------------------------------
# Number formatting
# --------------------------------------------------------------------------------------


def fmt_money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    av = abs(v)
    sign = "-" if v < 0 else ""
    if av >= 1e12:
        return f"{sign}${av / 1e12:.2f}T"
    if av >= 1e9:
        return f"{sign}${av / 1e9:.2f}B"
    if av >= 1e6:
        return f"{sign}${av / 1e6:.2f}M"
    if av >= 1e3:
        return f"{sign}${av / 1e3:.2f}K"
    return f"{sign}${av:.2f}"


def fmt_pct(v: Optional[float], decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v * 100:+.{decimals}f}%"


def fmt_ratio(v: Optional[float], decimals: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:.{decimals}f}"


def fmt_score(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.0f}"


def score_bar(score: Optional[float], width: int = 20) -> str:
    if score is None:
        return "░" * width
    filled = int(round((score / 100) * width))
    return "█" * filled + "░" * (width - filled)


def score_color(score: Optional[float]) -> str:
    if score is None:
        return "dim"
    if score >= 80:
        return "bright_green"
    if score >= 65:
        return "green"
    if score >= 45:
        return "yellow"
    if score >= 30:
        return "red"
    return "bright_red"


# --------------------------------------------------------------------------------------
# Section renderers
# --------------------------------------------------------------------------------------


def render_movers(console: Console, movers: list[MoverSnapshot]) -> None:
    if not movers:
        console.print(Panel("Top movers unavailable.", title="Top 5 Gainers", style="dim"))
        return
    table = Table(title="Top 5 Gainers Today", header_style="bold", expand=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("Ticker", style="bold cyan")
    table.add_column("Name")
    table.add_column("Price", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Headline", overflow="fold")
    for i, m in enumerate(movers, 1):
        change = (
            f"[bright_green]+{m.change_pct:.2f}%[/]" if m.change_pct and m.change_pct >= 0
            else f"[red]{m.change_pct:.2f}%[/]" if m.change_pct is not None else "—"
        )
        table.add_row(
            str(i),
            m.ticker or "—",
            (m.name or "")[:40],
            fmt_money(m.price),
            change,
            (m.headline or "")[:80],
        )
    console.print(table)


def _header_panel(fin: Financials) -> Panel:
    c = fin.company
    p = fin.price
    sub = " · ".join(filter(None, [
        c.sector, c.industry, f"Mkt Cap {fmt_money(c.market_cap)}",
        f"EV {fmt_money(c.enterprise_value)}",
    ]))
    price_line = f"[bold]{fmt_money(p.current)}[/]"
    if p.change_today_pct is not None:
        sign = "+" if p.change_today_pct >= 0 else ""
        color = "bright_green" if p.change_today_pct >= 0 else "red"
        price_line += f"   [{color}]{sign}{p.change_today_pct * 100:.2f}% today[/]"
    body_markup = f"{sub}\n{price_line}"
    catalyst_parts: list[str] = []
    today = _date.today()
    if fin.next_earnings_date:
        days = (fin.next_earnings_date - today).days
        ed_str = fin.next_earnings_date.strftime("%b %d")
        if 0 <= days <= 10:
            catalyst_parts.append(f"[bold red]⚠ Earnings in {days}d ({ed_str})[/]")
        else:
            catalyst_parts.append(f"Earnings: {ed_str}")
    if fin.ex_dividend_date:
        catalyst_parts.append(f"Ex-Div: {fin.ex_dividend_date.strftime('%b %d')}")
    if catalyst_parts:
        body_markup += "\n" + "  ·  ".join(catalyst_parts)
    body = Text.from_markup(body_markup)
    title = f"[bold cyan]{c.ticker}[/] · {c.name} · {c.exchange or ''}"
    return Panel(body, title=title, border_style="cyan")


def _scorecard_table(scorecard: Scorecard) -> Table:
    t = Table(title=f"Financial Health Score   [bold]{fmt_score(scorecard.overall)} / 100   ({scorecard.band})[/]", expand=True, show_lines=False)
    t.add_column("Category", style="bold")
    t.add_column("Score", justify="right", width=6)
    t.add_column("Bar", width=22)
    for c in scorecard.categories:
        color = score_color(c.score)
        t.add_row(c.name, f"[{color}]{fmt_score(c.score)}[/]", f"[{color}]{score_bar(c.score)}[/]")
    return t


def _bullets_panel(title: str, items: list[str], style: str) -> Panel:
    if not items:
        body = Text("(none)", style="dim")
    else:
        lines = [Text.from_markup(f"• {item}") for item in items]
        body = Text("\n").join(lines)
    return Panel(body, title=title, border_style=style)


def _business_overview_panel(fin: Financials) -> Optional[Panel]:
    s = fin.company.business_summary
    if not s or len(s) < 50:
        return None
    return Panel(Text(s), title=f"About {fin.company.name}", border_style="dim")


def _ownership_panel(fin: Financials) -> Optional[Panel]:
    if not fin.top_institutional_holders:
        return None
    t = Table(box=None, show_header=True, padding=(0, 1))
    t.add_column("Institution", style="bold")
    t.add_column("% Owned", justify="right")
    t.add_column("Shares", justify="right")
    for h in fin.top_institutional_holders:
        pct_str = f"{h['pct'] * 100:.2f}%" if h["pct"] else "—"
        t.add_row(h["name"], pct_str, fmt_money(h["shares"]))
    inst_pct = fin.institutional_ownership_pct
    title = "Ownership"
    if inst_pct:
        title += f"  · Institutions {inst_pct * 100:.1f}%"
    return Panel(t, title=title, border_style="cyan")


def _finra_panel(finra) -> Optional[Panel]:
    """Render short-sale z-score per-day table from FINRA CNMS consolidated data."""
    if finra is None:
        return None
    recent = finra.recent_days()
    if not recent:
        return None

    mean = finra.baseline_mean()
    std = finra.baseline_std()
    mean_str = f"{mean * 100:.1f}%" if mean is not None else "—"
    std_str = f"{std * 100:.1f}%" if std is not None else "—"
    baseline_line = Text.from_markup(
        f"[dim]30-day baseline · avg {mean_str}  std {std_str}[/]"
    )

    t = Table(show_header=True, header_style="dim", expand=True, box=None, padding=(0, 1))
    t.add_column("Date", style="dim")
    t.add_column("Short %", justify="right")
    t.add_column("Z-Score", justify="right")
    t.add_column("Signal", justify="center")

    _label_color = {"Bearish": "bright_red", "Bullish": "green", "Neutral": "yellow"}

    for d in recent:
        label = finra.day_label(d)
        z = finra.day_z_score(d)
        color = _label_color.get(label, "dim")
        z_str = f"[{color}]{z:+.2f}σ[/]" if z is not None else "[dim]—[/]"
        t.add_row(
            d.date.strftime("%b %d"),
            f"{d.short_pct * 100:.1f}%",
            z_str,
            f"[{color}]{label}[/]",
        )

    avg_z = finra.avg_z_score()
    direction = finra.directional_label()
    dir_color = _label_color.get(direction, "dim")
    z_avg_str = f"[{dir_color}]{avg_z:+.2f}σ[/]" if avg_z is not None else "[dim]—[/]"
    signal_line = Text.from_markup(
        f"Signal: [{dir_color}]{direction}[/]   avg z-score: {z_avg_str}"
    )
    if finra.fetch_error:
        signal_line.append(f"  ({finra.fetch_error})", style="dim")

    from rich.console import Group
    return Panel(
        Group(baseline_line, t, signal_line),
        title="Short Sale Activity  [dim](FINRA CNMS · 30-day z-score)[/]",
        border_style="magenta",
    )


def _earnings_table(fin: Financials) -> Optional[Table]:
    if not fin.earnings_records:
        return None
    t = Table(title="Recent Earnings (Last 4 Quarters)", expand=True)
    t.add_column("Quarter")
    t.add_column("EPS Est.", justify="right")
    t.add_column("EPS Act.", justify="right")
    t.add_column("Surprise", justify="right")
    t.add_column("Beat / Miss", justify="center", width=10)
    for r in fin.earnings_records:
        q_str = r.quarter.strftime("%b '%y") if r.quarter else "—"
        est = fmt_ratio(r.eps_estimate) if r.eps_estimate is not None else "—"
        act = fmt_ratio(r.eps_actual) if r.eps_actual is not None else "—"
        if r.surprise_pct is not None:
            sign = "+" if r.surprise_pct >= 0 else ""
            color = "bright_green" if r.surprise_pct > 0 else "red"
            surprise_str = f"[{color}]{sign}{r.surprise_pct:.2f}%[/]"
            beat_miss = f"[{color}]{'BEAT' if r.surprise_pct > 0 else 'MISS'}[/]"
        else:
            surprise_str = "[dim]—[/]"
            beat_miss = "[dim]—[/]"
        t.add_row(q_str, est, act, surprise_str, beat_miss)
    return t


_TREND_GLYPHS: dict[str, str] = {
    "flat": "[white]─[/]",
    "up_slight": "[pale_green1]>[/]",
    "up_strong": "[bright_green]>>[/]",
    "down_slight": "[light_salmon1]<[/]",
    "down_strong": "[bright_red]<<[/]",
}


def _trend_glyph(code: str) -> str:
    """Render a TrendStat.direction code as a colored rich-markup glyph."""
    return _TREND_GLYPHS.get(code, _TREND_GLYPHS["flat"])


def _key_metrics_table(fin: Financials, report: Report) -> Table:
    s = fin.stats
    peer_med = report.peers.medians if report.peers else {}
    rows: list[tuple[str, str, str, str]] = []  # (name, latest, trend, peer)
    def add(name: str, latest: str, trend: str = "flat", peer: Optional[float] = None, fmt=fmt_ratio):
        rows.append((name, latest, _trend_glyph(trend), fmt(peer) if peer is not None else "—"))
    add("P/E (TTM)", fmt_ratio(s.pe), peer=peer_med.get("pe"))
    add("Forward P/E", fmt_ratio(s.forward_pe), peer=peer_med.get("forward_pe"))
    add("PEG", fmt_ratio(s.peg), peer=peer_med.get("peg"))
    add("EV/EBITDA", fmt_ratio(s.ev_ebitda), peer=peer_med.get("ev_ebitda"))
    add("P/S", fmt_ratio(s.price_to_sales), peer=peer_med.get("price_to_sales"))
    add("P/B", fmt_ratio(s.price_to_book), peer=peer_med.get("price_to_book"))
    add("FCF Yield", fmt_pct(s.fcf_yield))
    add("Gross margin", fmt_pct(s.gross_margin), report.trends.gross_margin.direction, peer_med.get("gross_margin"), fmt=fmt_pct)
    add("Operating margin", fmt_pct(s.operating_margin), report.trends.operating_margin.direction, peer_med.get("operating_margin"), fmt=fmt_pct)
    add("Net margin", fmt_pct(s.net_margin), report.trends.net_margin.direction, peer_med.get("net_margin"), fmt=fmt_pct)
    if s.r_and_d_pct is not None:
        add("R&D / Revenue", fmt_pct(s.r_and_d_pct))
    add("ROE", fmt_pct(s.roe), peer=peer_med.get("roe"), fmt=fmt_pct)
    add("ROA", fmt_pct(s.roa), peer=peer_med.get("roa"), fmt=fmt_pct)
    add("ROIC (est.)", fmt_pct(s.roic))
    add("Debt / Equity", fmt_ratio(s.debt_to_equity), peer=peer_med.get("debt_to_equity"))
    add("Current ratio", fmt_ratio(s.current_ratio), peer=peer_med.get("current_ratio"))
    add("Interest coverage", fmt_ratio(s.interest_coverage))
    add("Dividend yield", fmt_pct(s.dividend_yield), peer=peer_med.get("dividend_yield"), fmt=fmt_pct)

    t = Table(title="Key Metrics", expand=True)
    t.add_column("Metric", style="bold")
    t.add_column("Latest", justify="right")
    t.add_column("Trend", justify="center", width=6)
    t.add_column("Peer median", justify="right")
    if report.peers and report.peers.tickers:
        t.caption = "Peer median vs: " + " · ".join(report.peers.tickers[:6])
    for name, latest, trend, peer in rows:
        t.add_row(name, latest, trend, peer)
    return t


def _trend_table(report: Report) -> Table:
    t = Table(title="Multi-Year Trend Analysis", expand=True)
    t.add_column("Metric", style="bold")
    t.add_column("YoY", justify="right")
    t.add_column("3y CAGR", justify="right")
    t.add_column("Direction", justify="center", width=10)
    rows = [
        ("Revenue", report.trends.revenue.yoy, report.trends.revenue.cagr_3y, report.trends.revenue.direction),
        ("EPS (diluted)", report.trends.eps_diluted.yoy, report.trends.eps_diluted.cagr_3y, report.trends.eps_diluted.direction),
        ("Free Cash Flow", report.trends.free_cash_flow.yoy, report.trends.free_cash_flow.cagr_3y, report.trends.free_cash_flow.direction),
        ("Net Income", report.trends.net_income.yoy, report.trends.net_income.cagr_3y, report.trends.net_income.direction),
        ("Operating Margin (Δ)", report.trends.operating_margin.yoy, None, report.trends.operating_margin.direction),
    ]
    for name, yoy, cagr, direction in rows:
        t.add_row(name, fmt_pct(yoy), fmt_pct(cagr) if cagr is not None else "—", _trend_glyph(direction))
    return t


def _risk_panel(report: Report) -> Panel:
    if not report.risk_flags:
        body = Text("No material red flags detected.", style="dim green")
    else:
        lines = []
        sev_color = {"low": "yellow", "medium": "red", "high": "bright_red"}
        for f in report.risk_flags:
            c = sev_color.get(f.severity, "yellow")
            lines.append(Text.from_markup(f"[{c}]⚠ {f.name}[/] — {f.detail}"))
        body = Text("\n").join(lines)
    return Panel(body, title="Risk Analysis", border_style="red")


def _direction_panel(report: Report) -> Panel:
    n = report.narrative
    color = {"BUY": "bright_green", "HOLD": "yellow", "SELL": "red"}.get(n.direction, "white")
    title = f"Final Direction: [{color}]{n.direction}[/]   ({n.confidence} confidence)"
    body = Text.from_markup(
        f"{n.rationale}\n\n[dim]{DISCLAIMER}[/]"
    )
    return Panel(body, title=title, border_style=color)


_TONE_GLYPHS = {
    "positive": "[green]▲ pos[/]",
    "negative": "[red]▼ neg[/]",
    "neutral": "[dim]─ neu[/]",
}


def _headline_cell(item) -> str:
    """Render a headline as clickable text via rich's OSC 8 link markup.

    Rich escapes any `[` characters inside the title so the markup parser doesn't
    misinterpret them. Falls back to plain title text when no URL is available.
    """
    title = item.title.replace("[", r"\[")
    if item.url:
        return f"[link={item.url}]{title}[/link]"
    return title


def _sentiment_table(report: Report) -> Table:
    tone = report.sentiment.tone_summary()
    title = (
        f"Recent Coverage  ([green]{tone['positive']}+[/] / "
        f"[dim]{tone['neutral']}=[/] / [red]{tone['negative']}-[/]"
        f"  net {tone['net']:+.2f})"
    )
    t = Table(title=title, expand=True)
    t.add_column("Tier", style="bold")
    t.add_column("Source", style="cyan")
    t.add_column("Tone", justify="center", width=8)
    t.add_column("Headline", overflow="fold")
    for item in report.sentiment.reliable[:6]:
        t.add_row(
            "[green]reliable[/]",
            item.source,
            _TONE_GLYPHS.get(item.sentiment_label, "[dim]─[/]"),
            _headline_cell(item),
        )
    for item in report.sentiment.social[:4]:
        t.add_row(
            "[yellow]social[/]",
            item.source,
            _TONE_GLYPHS.get(item.sentiment_label, "[dim]─[/]"),
            _headline_cell(item),
        )
    return t


# --------------------------------------------------------------------------------------
# Top-level
# --------------------------------------------------------------------------------------


def render_report(console: Console, report: Report) -> None:
    fin = report.fin
    n = report.narrative

    console.print(_header_panel(fin))

    overview = _business_overview_panel(fin)
    if overview:
        console.print(overview)

    if n.executive_summary:
        console.print(Panel(Text(n.executive_summary), title="Executive Summary", border_style="cyan"))

    console.print(_scorecard_table(report.scorecard))

    bull = _bullets_panel("Bullish Indicators", n.bullish, "green")
    bear = _bullets_panel("Bearish Indicators", n.bearish, "red")
    console.print(bull)
    console.print(bear)

    ownership = _ownership_panel(fin)
    if ownership:
        console.print(ownership)

    finra_panel = _finra_panel(getattr(report, "finra", None))
    if finra_panel:
        console.print(finra_panel)

    console.print(_key_metrics_table(fin, report))
    console.print(_trend_table(report))

    earnings = _earnings_table(fin)
    if earnings:
        console.print(earnings)

    if n.valuation_paragraph:
        console.print(Panel(Text(n.valuation_paragraph), title="Valuation Assessment", border_style="cyan"))
    if n.balance_sheet_paragraph:
        console.print(Panel(Text(n.balance_sheet_paragraph), title="Balance Sheet Assessment", border_style="cyan"))
    if n.cash_flow_paragraph:
        console.print(Panel(Text(n.cash_flow_paragraph), title="Cash Flow Assessment", border_style="cyan"))
    if n.competitive_paragraph:
        console.print(Panel(Text(n.competitive_paragraph), title="Competitive Positioning", border_style="cyan"))

    console.print(_sentiment_table(report))
    console.print(_risk_panel(report))
    if report.sentiment.failed_sources:
        console.print(Text(
            f"(unavailable sources: {', '.join(report.sentiment.failed_sources)})",
            style="dim",
        ))
    console.print(_direction_panel(report))


def render_market_closed(console: Console, reason: str, as_of) -> None:
    console.print(
        Panel(
            Text.from_markup(
                f"NYSE is closed today ({as_of}, reason: {reason}).\n"
                "Top-movers fetch skipped. Enter a ticker for a full report."
            ),
            title="Market Closed",
            border_style="yellow",
        )
    )


def render_rule(console: Console, label: str = "") -> None:
    console.print(Rule(label))
