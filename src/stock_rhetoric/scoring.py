"""Deterministic 0-100 scoring across 7 categories.

Each rule maps a metric value to a 0-100 score using simple piecewise-linear
threshold functions. Category scores are weighted averages of their rules.
Overall is a weighted average of categories.

The LLM never writes scores; the LLM only narrates them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from .financials import Financials
from .peers import PeerSet
from .trends import TrendReport


# --------------------------------------------------------------------------------------
# Score data model
# --------------------------------------------------------------------------------------


@dataclass
class RuleResult:
    name: str
    value: Optional[float]    # the raw input value (for display)
    score: Optional[float]    # 0-100; None if data unavailable
    weight: float
    why: str


@dataclass
class CategoryScore:
    name: str
    score: Optional[float]    # 0-100 weighted avg of rules with score ≠ None
    rules: list[RuleResult] = field(default_factory=list)


@dataclass
class Scorecard:
    overall: Optional[float]
    categories: list[CategoryScore]
    band: str   # "Strong", "Healthy", "Mixed", "Weak", "Distressed"


CATEGORY_WEIGHTS: dict[str, float] = {
    "Growth": 20,
    "Profitability": 15,
    "Financial Stability": 15,
    "Cash Flow Health": 15,
    "Valuation": 15,
    "Shareholder Returns": 10,
    "Operational Efficiency": 10,
}


# --------------------------------------------------------------------------------------
# Score-mapping helpers
# --------------------------------------------------------------------------------------


def linmap(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Map v ∈ [lo, hi] → 0..100. Outside → clamped."""
    if v is None:
        return None
    if hi == lo:
        return 50.0
    s = (v - lo) / (hi - lo) * 100
    return max(0.0, min(100.0, s))


def linmap_inverse(v: Optional[float], lo: float, hi: float) -> Optional[float]:
    """Map v ∈ [lo, hi] → 100..0. (Lower v is better.)"""
    s = linmap(v, lo, hi)
    return None if s is None else 100 - s


def tent(v: Optional[float], peak: float, half_width: float) -> Optional[float]:
    """Triangular tent: 100 at peak, 0 at peak±half_width."""
    if v is None:
        return None
    dist = abs(v - peak)
    if dist >= half_width:
        return 0.0
    return (1 - dist / half_width) * 100


def _weighted_avg(rules: list[RuleResult]) -> Optional[float]:
    scored = [(r.score, r.weight) for r in rules if r.score is not None]
    if not scored:
        return None
    total_w = sum(w for _, w in scored)
    if total_w == 0:
        return None
    return sum(s * w for s, w in scored) / total_w


def _rule(name: str, value: Optional[float], score_fn: Callable[[Optional[float]], Optional[float]], weight: float, why: str) -> RuleResult:
    return RuleResult(name=name, value=value, score=score_fn(value), weight=weight, why=why)


# --------------------------------------------------------------------------------------
# Category scorers
# --------------------------------------------------------------------------------------


def score_growth(fin: Financials, trends: TrendReport) -> CategoryScore:
    rules = [
        _rule(
            "Revenue 3y CAGR",
            trends.revenue.cagr_3y,
            lambda v: linmap(v, 0.0, 0.30),
            weight=3,
            why="Sustained top-line growth is the foundation of long-term value.",
        ),
        _rule(
            "Revenue YoY",
            trends.revenue.yoy,
            lambda v: linmap(v, -0.05, 0.25),
            weight=3,
            why="Recent growth pace tells us whether the business is accelerating or stalling.",
        ),
        _rule(
            "EPS 3y CAGR",
            trends.eps_diluted.cagr_3y,
            lambda v: linmap(v, 0.0, 0.25),
            weight=2,
            why="EPS growth links top-line gains to actual shareholder returns.",
        ),
        _rule(
            "FCF 3y CAGR",
            trends.free_cash_flow.cagr_3y,
            lambda v: linmap(v, 0.0, 0.25),
            weight=2,
            why="FCF growth confirms growth is funded by operations, not financing.",
        ),
    ]
    return CategoryScore("Growth", _weighted_avg(rules), rules)


def score_profitability(fin: Financials, trends: TrendReport) -> CategoryScore:
    s = fin.stats
    # Margin trend (latest - 3y ago) in percentage points
    margin_change = None
    if len(trends.operating_margin.series) >= 4:
        margin_change = trends.operating_margin.series[-1] - trends.operating_margin.series[-4]
    rules = [
        _rule(
            "Gross margin",
            s.gross_margin,
            lambda v: linmap(v, 0.10, 0.60),
            weight=2,
            why="Gross margin signals pricing power and product economics.",
        ),
        _rule(
            "Operating margin",
            s.operating_margin,
            lambda v: linmap(v, 0.0, 0.30),
            weight=3,
            why="Operating margin reflects efficiency below pricing — cost control + scale.",
        ),
        _rule(
            "Net margin",
            s.net_margin,
            lambda v: linmap(v, 0.0, 0.25),
            weight=2,
            why="Net margin captures profitability after interest, taxes, and one-offs.",
        ),
        _rule(
            "EBITDA margin",
            s.ebitda_margin,
            lambda v: linmap(v, 0.05, 0.35),
            weight=2,
            why="EBITDA margin highlights core operating profitability across capital structures.",
        ),
        _rule(
            "Operating margin 3y change",
            margin_change,
            lambda v: linmap(v, -0.05, 0.10),
            weight=3,
            why="Direction of margins matters as much as level — expansion is a quality signal.",
        ),
    ]
    return CategoryScore("Profitability", _weighted_avg(rules), rules)


def score_stability(fin: Financials, trends: TrendReport) -> CategoryScore:
    s = fin.stats
    # yfinance reports debtToEquity as a percentage (e.g., 150 = 1.5×). Normalize:
    de = s.debt_to_equity / 100 if s.debt_to_equity and s.debt_to_equity > 5 else s.debt_to_equity
    # Debt growth YoY
    debt_yoy = None
    a = fin.annual
    if len(a) >= 2 and a[-1].total_debt is not None and a[-2].total_debt:
        debt_yoy = (a[-1].total_debt - a[-2].total_debt) / abs(a[-2].total_debt)
    rules = [
        _rule(
            "Debt / Equity",
            de,
            lambda v: linmap_inverse(v, 0.3, 2.5),
            weight=3,
            why="Lower leverage means less default risk and more financial flexibility.",
        ),
        _rule(
            "Current ratio",
            s.current_ratio,
            lambda v: tent(v, peak=2.0, half_width=1.5),
            weight=2,
            why="Short-term liquidity — too low risks distress, too high suggests idle capital.",
        ),
        _rule(
            "Quick ratio",
            s.quick_ratio,
            lambda v: linmap(v, 0.5, 1.5),
            weight=2,
            why="Liquidity excluding inventory — a stricter solvency check.",
        ),
        _rule(
            "Interest coverage",
            s.interest_coverage,
            lambda v: linmap(v, 1.5, 10.0),
            weight=3,
            why="Operating income vs interest expense — below 3× signals refinancing risk.",
        ),
        _rule(
            "Debt growth YoY",
            debt_yoy,
            lambda v: linmap_inverse(v, -0.10, 0.40),
            weight=2,
            why="Rapid debt growth without matching FCF is a leverage warning.",
        ),
    ]
    return CategoryScore("Financial Stability", _weighted_avg(rules), rules)


def score_cash_flow(fin: Financials, trends: TrendReport) -> CategoryScore:
    a = fin.annual
    fcf_positive = None
    if a and a[-1].free_cash_flow is not None:
        fcf_positive = 1.0 if a[-1].free_cash_flow > 0 else 0.0
    # Earnings quality = OCF / NI
    ocf_ni = None
    if a and a[-1].operating_cash_flow and a[-1].net_income:
        ocf_ni = a[-1].operating_cash_flow / a[-1].net_income
    # Capex / OCF (lower = lighter capital burden)
    capex_burden = None
    if a and a[-1].operating_cash_flow and a[-1].capex is not None:
        if a[-1].operating_cash_flow > 0:
            capex_burden = abs(a[-1].capex) / a[-1].operating_cash_flow
    rules = [
        _rule(
            "FCF positive (latest year)",
            fcf_positive,
            lambda v: 100.0 if v == 1.0 else (0.0 if v == 0.0 else None),
            weight=3,
            why="Positive free cash flow means the business funds itself.",
        ),
        _rule(
            "FCF 3y CAGR",
            trends.free_cash_flow.cagr_3y,
            lambda v: linmap(v, -0.05, 0.30),
            weight=3,
            why="Compounding FCF is the strongest indicator of durable value creation.",
        ),
        _rule(
            "OCF / Net Income",
            ocf_ni,
            lambda v: tent(v, peak=1.1, half_width=1.0),
            weight=3,
            why="OCF below NI signals accruals — earnings quality concern.",
        ),
        _rule(
            "Capex / OCF",
            capex_burden,
            lambda v: linmap_inverse(v, 0.10, 0.80),
            weight=2,
            why="High capex burden leaves less cash for shareholders or debt paydown.",
        ),
    ]
    return CategoryScore("Cash Flow Health", _weighted_avg(rules), rules)


def score_valuation(fin: Financials, trends: TrendReport, peers: Optional[PeerSet]) -> CategoryScore:
    s = fin.stats
    # Relative-to-peer rules — only score if we have a peer median.
    pm = peers.medians if peers else {}

    def rel_inverse(v: Optional[float], peer_v: Optional[float]) -> Optional[float]:
        """Score = 100 when v <= 0.6×peer, 0 when v >= 1.6×peer."""
        if v is None or peer_v is None or peer_v <= 0:
            return None
        ratio = v / peer_v
        return linmap_inverse(ratio, 0.6, 1.6)

    rules = [
        _rule(
            "P/E (TTM)",
            s.pe,
            lambda v: linmap_inverse(v, 8, 45),
            weight=2,
            why="Lower P/E means cheaper earnings (context-dependent — pair with growth).",
        ),
        _rule(
            "P/E vs peer median",
            s.pe,
            lambda v: rel_inverse(v, pm.get("pe")),
            weight=3,
            why="Premium vs peers must be justified by superior growth or returns.",
        ),
        _rule(
            "Forward P/E",
            s.forward_pe,
            lambda v: linmap_inverse(v, 8, 35),
            weight=2,
            why="Forward P/E adjusts for expected earnings growth.",
        ),
        _rule(
            "PEG",
            s.peg,
            lambda v: linmap_inverse(v, 0.5, 3.0),
            weight=2,
            why="Growth-adjusted P/E — PEG ≤ 1 is classically attractive.",
        ),
        _rule(
            "EV/EBITDA",
            s.ev_ebitda,
            lambda v: linmap_inverse(v, 5, 25),
            weight=2,
            why="Capital-structure-neutral valuation; useful across industries.",
        ),
        _rule(
            "FCF Yield",
            s.fcf_yield,
            lambda v: linmap(v, 0.0, 0.08),
            weight=3,
            why="FCF / market cap — the most cash-grounded valuation signal.",
        ),
        _rule(
            "P/S vs peer median",
            s.price_to_sales,
            lambda v: rel_inverse(v, pm.get("price_to_sales")),
            weight=1,
            why="Useful when earnings are noisy; compare to peers, not absolutes.",
        ),
    ]
    return CategoryScore("Valuation", _weighted_avg(rules), rules)


def score_shareholder(fin: Financials, trends: TrendReport) -> CategoryScore:
    s = fin.stats
    # Dilution / buyback signal via shares outstanding YoY (annual)
    a = fin.annual
    so_yoy = None
    if len(a) >= 2 and a[-1].shares_outstanding and a[-2].shares_outstanding:
        so_yoy = (a[-1].shares_outstanding - a[-2].shares_outstanding) / a[-2].shares_outstanding
    rules = [
        _rule(
            "Dividend yield",
            s.dividend_yield,
            lambda v: linmap(v, 0.0, 0.04),
            weight=2,
            why="Cash returned to shareholders; not the only form of return but a tangible one.",
        ),
        _rule(
            "Payout ratio",
            s.payout_ratio,
            lambda v: tent(v, peak=0.40, half_width=0.50),
            weight=2,
            why="Payout in a healthy band — too high is unsustainable, zero may mean no return.",
        ),
        _rule(
            "Share count YoY (buybacks)",
            so_yoy,
            # Negative = buybacks (good); positive = dilution (bad). Map -5% → 100, +3% → 0.
            lambda v: linmap_inverse(v, -0.05, 0.03),
            weight=3,
            why="Falling share count amplifies per-share returns; rising count dilutes them.",
        ),
    ]
    return CategoryScore("Shareholder Returns", _weighted_avg(rules), rules)


def score_efficiency(fin: Financials, trends: TrendReport) -> CategoryScore:
    s = fin.stats
    # ROE trend
    roe_change = None
    a = fin.annual
    if len(a) >= 4:
        def _roe(p):
            if p.net_income and p.total_equity:
                return p.net_income / p.total_equity
            return None
        roes = [_roe(p) for p in a[-4:]]
        if all(r is not None for r in roes):
            roe_change = roes[-1] - roes[0]
    rules = [
        _rule(
            "ROE",
            s.roe,
            lambda v: linmap(v, 0.05, 0.30),
            weight=3,
            why="Return on equity — how much profit management generates per $ of equity.",
        ),
        _rule(
            "ROA",
            s.roa,
            lambda v: linmap(v, 0.01, 0.15),
            weight=2,
            why="Return on assets — efficiency across the whole balance sheet.",
        ),
        _rule(
            "ROIC",
            s.roic,
            lambda v: linmap(v, 0.05, 0.25),
            weight=3,
            why="Return on invested capital — the cleanest read on capital allocation.",
        ),
        _rule(
            "Asset turnover",
            s.asset_turnover,
            lambda v: linmap(v, 0.3, 1.5),
            weight=1,
            why="Sales per $ of assets; varies by industry but trend is informative.",
        ),
        _rule(
            "ROE 3y change",
            roe_change,
            lambda v: linmap(v, -0.10, 0.10),
            weight=1,
            why="Direction of returns indicates whether competitive position is improving.",
        ),
    ]
    return CategoryScore("Operational Efficiency", _weighted_avg(rules), rules)


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def _band(score: Optional[float]) -> str:
    if score is None:
        return "Unscored"
    if score >= 80:
        return "Strong"
    if score >= 65:
        return "Healthy"
    if score >= 45:
        return "Mixed"
    if score >= 30:
        return "Weak"
    return "Distressed"


def score(fin: Financials, trends: TrendReport, peers: Optional[PeerSet]) -> Scorecard:
    categories = [
        score_growth(fin, trends),
        score_profitability(fin, trends),
        score_stability(fin, trends),
        score_cash_flow(fin, trends),
        score_valuation(fin, trends, peers),
        score_shareholder(fin, trends),
        score_efficiency(fin, trends),
    ]
    # Overall: weighted average of categories that have a score
    pairs = [(c.score, CATEGORY_WEIGHTS[c.name]) for c in categories if c.score is not None]
    overall = None
    if pairs:
        total_w = sum(w for _, w in pairs)
        if total_w > 0:
            overall = sum(s * w for s, w in pairs) / total_w
    return Scorecard(overall=overall, categories=categories, band=_band(overall))
