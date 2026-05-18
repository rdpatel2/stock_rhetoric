"""Educational `--help` companion: what numeric stats make a stock worth a closer look.

Rendered when the user passes `--help` to the CLI. Pure text — no network, no ticker
required. Thresholds quoted here are sector-agnostic baselines; the report itself
benchmarks against peers for sector-aware reads.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .render import DISCLAIMER


_SECTIONS: list[tuple[str, str, list[str]]] = [
    (
        "Growth",
        "green",
        [
            "[bold]Revenue YoY[/] > ~8% (sector-dependent — software/AI/biotech expect more, utilities much less).",
            "[bold]Revenue 3y CAGR[/] > ~10% with the latest year [italic]not[/] decelerating sharply vs the CAGR.",
            "[bold]Diluted EPS[/] growing at least in line with revenue — margin leverage is a plus.",
            "Beware: top-line growth that doesn't translate to free cash flow.",
        ],
    ),
    (
        "Profitability & margins",
        "green",
        [
            "[bold]Gross margin[/] [italic]expanding[/] over multiple years — signal of pricing power and durable moat.",
            "[bold]Operating margin[/] > sector median (rough generic baseline ~15%).",
            "[bold]Net margin[/] > ~8% (generic baseline; software/luxury can clear 20%+).",
            "[bold]ROE[/] > ~15% sustained; ROA > ~5%; ROIC > cost of capital (~8–10%).",
        ],
    ),
    (
        "Valuation",
        "cyan",
        [
            "[bold]P/E (TTM)[/] vs sector median — a premium needs to be justified by growth or quality.",
            "[bold]PEG[/] < ~1.5 for growers; below 1.0 is genuinely cheap if the growth is real.",
            "[bold]EV/EBITDA[/] < ~15 for mature businesses; growth stocks trade higher.",
            "[bold]Price/Sales[/] sanity check for unprofitable growth (under 10× even for SaaS).",
            "[bold]FCF yield[/] > ~5% — cash returns to shareholders before any buybacks/dividends.",
        ],
    ),
    (
        "Balance sheet & liquidity",
        "yellow",
        [
            "[bold]Debt/Equity[/] < ~1.0 (industry-dependent: utilities and REITs run higher; cash-rich tech runs near zero).",
            "[bold]Current ratio[/] > 1.5 (can cover near-term obligations 1.5×).",
            "[bold]Interest coverage[/] > 5× (EBIT divided by interest expense) — survives rate hikes and slowdowns.",
        ],
    ),
    (
        "Cash flow quality",
        "green",
        [
            "[bold]Free cash flow[/] positive and growing in absolute terms.",
            "[bold]FCF / Net Income[/] > ~0.8 — a low ratio means earnings aren't translating into cash (red flag).",
            "[bold]Operating cash flow[/] tracking (not lagging) reported net income over multiple years.",
        ],
    ),
    (
        "Shareholder returns",
        "cyan",
        [
            "[bold]Dividend yield[/] is sustainable when [bold]payout ratio[/] < ~70%.",
            "[bold]Share count declining[/] over time — buybacks outpacing dilution.",
            "Watch: buybacks funded by [italic]new debt[/] (extracts value short-term, weakens balance sheet).",
        ],
    ),
    (
        "Red flags to watch",
        "red",
        [
            "[bold]Margin compression[/] across consecutive years — pricing power eroding.",
            "[bold]FCF declining while EPS rises[/] — earnings quality concern (accruals, one-offs).",
            "[bold]Share dilution[/] without commensurate revenue growth.",
            "[bold]Valuation premium without growth[/] — multiples richer than peers, growth in line or below.",
            "[bold]Low interest coverage[/] (< 3×) combined with high D/E — refinancing risk.",
        ],
    ),
    (
        "How to read this report",
        "white",
        [
            "[bold]Score bands[/]: 80+ Strong · 65–79 Healthy · 45–64 Mixed · 30–44 Weak · <30 Distressed.",
            "[bold]Trend glyphs[/]: [white]─[/] flat · [pale_green1]>[/] slight up · [bright_green]>>[/] strong up · [light_salmon1]<[/] slight down · [bright_red]<<[/] strong down. Bands: <2% flat, 2–25% slight, ≥25% strong (end-to-end).",
            "[bold]Recent Coverage Tone[/]: aggregate of headline sentiment across reliable + social sources. Net is the average compound score (−1.0 to +1.0).",
        ],
    ),
]


def render_guide(console: Console) -> None:
    """Render the full educational guide as a series of rich panels."""
    intro = Text.from_markup(
        "[bold]What to look for in a lucrative stock[/]\n"
        "[dim]Quick reference: the numeric anchors behind each section of the report. "
        "Thresholds are sector-agnostic baselines — the report itself benchmarks against peers.[/]"
    )
    console.print(intro)
    console.print()
    for title, color, bullets in _SECTIONS:
        lines = [Text.from_markup(f"• {item}") for item in bullets]
        body = Text("\n").join(lines)
        console.print(Panel(body, title=title, border_style=color))
    console.print()
    console.print(Text(DISCLAIMER, style="dim"))
