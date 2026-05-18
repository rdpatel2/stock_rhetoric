"""Red-flag detection. Each rule is a pure function over Financials/TrendReport/PeerSet."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .financials import Financials
from .peers import PeerSet
from .trends import TrendReport


@dataclass
class RiskFlag:
    name: str
    severity: str   # "low", "medium", "high"
    detail: str


def _flag(name: str, severity: str, detail: str) -> RiskFlag:
    return RiskFlag(name=name, severity=severity, detail=detail)


def detect(fin: Financials, trends: TrendReport, peers: Optional[PeerSet]) -> list[RiskFlag]:
    flags: list[RiskFlag] = []
    s = fin.stats
    a = fin.annual

    # Margin compression: operating margin down ≥ 2pp over 3 years
    series = trends.operating_margin.series
    if len(series) >= 4 and (series[-1] - series[-4]) < -0.02:
        flags.append(_flag(
            "Margin compression",
            "medium",
            f"Operating margin fell {(series[-4] - series[-1]) * 100:.1f}pp over 3 years.",
        ))

    # Revenue contraction (latest year)
    if trends.revenue.yoy is not None and trends.revenue.yoy < -0.02:
        flags.append(_flag(
            "Revenue contraction",
            "high",
            f"Revenue down {abs(trends.revenue.yoy) * 100:.1f}% YoY.",
        ))

    # Declining FCF
    if trends.free_cash_flow.yoy is not None and trends.free_cash_flow.yoy < -0.10:
        flags.append(_flag(
            "Declining FCF",
            "medium",
            f"Free cash flow fell {abs(trends.free_cash_flow.yoy) * 100:.0f}% YoY.",
        ))

    # Negative OCF (latest year)
    if a and a[-1].operating_cash_flow is not None and a[-1].operating_cash_flow < 0:
        flags.append(_flag(
            "Negative operating cash flow",
            "high",
            f"Operating cash flow was ${a[-1].operating_cash_flow / 1e9:.2f}B in the last year.",
        ))

    # D/E rising > 25% YoY
    if len(a) >= 2 and a[-1].total_debt and a[-2].total_debt:
        debt_yoy = (a[-1].total_debt - a[-2].total_debt) / abs(a[-2].total_debt)
        if debt_yoy > 0.25:
            flags.append(_flag(
                "Rapid debt growth",
                "medium",
                f"Total debt rose {debt_yoy * 100:.0f}% YoY.",
            ))

    # Weak liquidity
    if s.current_ratio is not None and s.current_ratio < 1.0:
        flags.append(_flag(
            "Weak liquidity",
            "high",
            f"Current ratio {s.current_ratio:.2f} (< 1.0).",
        ))

    # Low interest coverage
    if s.interest_coverage is not None and s.interest_coverage < 3.0:
        flags.append(_flag(
            "Low interest coverage",
            "high",
            f"Operating income covers interest only {s.interest_coverage:.1f}× (< 3×).",
        ))

    # Dilution: shares up > 3% YoY
    if len(a) >= 2 and a[-1].shares_outstanding and a[-2].shares_outstanding:
        so_yoy = (a[-1].shares_outstanding - a[-2].shares_outstanding) / a[-2].shares_outstanding
        if so_yoy > 0.03:
            flags.append(_flag(
                "Share dilution",
                "medium",
                f"Share count rose {so_yoy * 100:.1f}% YoY.",
            ))

    # Declining ROE — 3 consecutive years
    if len(a) >= 4:
        def _roe(p):
            if p.net_income and p.total_equity:
                return p.net_income / p.total_equity
            return None
        roes = [_roe(p) for p in a[-4:]]
        if all(r is not None for r in roes):
            if roes[0] > roes[1] > roes[2] > roes[3]:
                flags.append(_flag(
                    "Declining ROE",
                    "medium",
                    f"ROE fell 3 straight years (from {roes[0]*100:.1f}% to {roes[3]*100:.1f}%).",
                ))

    # Earnings-quality divergence: NI growing while FCF shrinks
    if (
        trends.net_income.yoy is not None
        and trends.free_cash_flow.yoy is not None
        and trends.net_income.yoy > 0.05
        and trends.free_cash_flow.yoy < -0.05
    ):
        flags.append(_flag(
            "Earnings-quality divergence",
            "medium",
            "Net income rising while free cash flow falls — possible accruals issue.",
        ))

    # Overvaluation vs peers (P/E > 1.5× peer median AND lower growth than peers — peer growth not directly available;
    # approximate: just flag the P/E premium and let the LLM weigh it)
    if peers and peers.medians.get("pe") and s.pe:
        if s.pe > peers.medians["pe"] * 1.5:
            flags.append(_flag(
                "Valuation premium vs peers",
                "low",
                f"P/E {s.pe:.1f} is {s.pe / peers.medians['pe']:.1f}× peer median ({peers.medians['pe']:.1f}).",
            ))

    # Debt-funded buybacks: shares down + total debt up + FCF flat-or-down
    if len(a) >= 2:
        cur, prev = a[-1], a[-2]
        if (
            cur.shares_outstanding and prev.shares_outstanding
            and cur.total_debt and prev.total_debt
            and cur.free_cash_flow is not None and prev.free_cash_flow is not None
        ):
            so_change = (cur.shares_outstanding - prev.shares_outstanding) / prev.shares_outstanding
            debt_change = (cur.total_debt - prev.total_debt) / abs(prev.total_debt)
            fcf_change = (cur.free_cash_flow - prev.free_cash_flow) / abs(prev.free_cash_flow or 1)
            if so_change < -0.01 and debt_change > 0.10 and fcf_change <= 0:
                flags.append(_flag(
                    "Debt-funded buybacks",
                    "medium",
                    "Shares retired while debt rose and FCF didn't grow — buybacks may be debt-financed.",
                ))

    return flags
