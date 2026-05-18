"""Trend analysis: CAGR, YoY, QoQ, direction, inflection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .financials import FinancialPeriod, Financials


@dataclass
class TrendStat:
    name: str
    series: list[float]   # oldest → newest
    yoy: Optional[float] = None
    cagr_3y: Optional[float] = None
    cagr_5y: Optional[float] = None
    direction: str = "flat"  # one of: flat, up_slight, up_strong, down_slight, down_strong


def _cagr(start: float, end: float, years: float) -> Optional[float]:
    if start is None or end is None or years <= 0:
        return None
    if start <= 0 or end <= 0:
        # Use sign-aware growth instead of CAGR when crossing zero.
        return None
    return (end / start) ** (1 / years) - 1


def _direction(series: list[float], flat_tol: float = 0.02, strong_tol: float = 0.25) -> str:
    """End-to-end change across the series, bucketed into five magnitude-aware bands.

    Bands:
      |change| <  flat_tol             → "flat"
      flat_tol ≤ change <  strong_tol  → "up_slight"
      change ≥ strong_tol              → "up_strong"
      -strong_tol < change ≤ -flat_tol → "down_slight"
      change ≤ -strong_tol             → "down_strong"
    """
    clean = [v for v in series if v is not None]
    if len(clean) < 2:
        return "flat"
    first, last = clean[0], clean[-1]
    if first == 0:
        # No baseline to scale against — flag direction by sign only.
        if last > 0:
            return "up_strong"
        if last < 0:
            return "down_strong"
        return "flat"
    change = (last - first) / abs(first)
    if change >= strong_tol:
        return "up_strong"
    if change >= flat_tol:
        return "up_slight"
    if change <= -strong_tol:
        return "down_strong"
    if change <= -flat_tol:
        return "down_slight"
    return "flat"


def _series(periods: list[FinancialPeriod], attr: str) -> list[float]:
    """Extract a non-None series for the given attribute (oldest → newest)."""
    return [getattr(p, attr) for p in periods if getattr(p, attr) is not None]


def trend_for(periods: list[FinancialPeriod], attr: str, label: str) -> TrendStat:
    series = _series(periods, attr)
    stat = TrendStat(name=label, series=series, direction=_direction(series))
    if len(series) >= 2:
        prev, last = series[-2], series[-1]
        if prev not in (None, 0):
            stat.yoy = (last - prev) / abs(prev)
    if len(series) >= 4:
        stat.cagr_3y = _cagr(series[-4], series[-1], 3)
    if len(series) >= 6:
        stat.cagr_5y = _cagr(series[-6], series[-1], 5)
    return stat


def margin_series(periods: list[FinancialPeriod], numerator: str, denominator: str = "revenue") -> list[float]:
    out: list[float] = []
    for p in periods:
        n = getattr(p, numerator)
        d = getattr(p, denominator)
        if n is None or not d:
            continue
        out.append(n / d)
    return out


def margin_trend(periods: list[FinancialPeriod], numerator: str, label: str) -> TrendStat:
    series = margin_series(periods, numerator)
    stat = TrendStat(name=label, series=series, direction=_direction(series, flat_tol=0.01))
    if len(series) >= 2:
        stat.yoy = series[-1] - series[-2]
    return stat


@dataclass
class TrendReport:
    revenue: TrendStat
    eps_diluted: TrendStat
    free_cash_flow: TrendStat
    operating_cash_flow: TrendStat
    net_income: TrendStat
    gross_margin: TrendStat
    operating_margin: TrendStat
    net_margin: TrendStat


def analyze(fin: Financials) -> TrendReport:
    """Compute the full trend report from annual statements."""
    a = fin.annual
    return TrendReport(
        revenue=trend_for(a, "revenue", "Revenue"),
        eps_diluted=trend_for(a, "eps_diluted", "EPS (diluted)"),
        free_cash_flow=trend_for(a, "free_cash_flow", "Free Cash Flow"),
        operating_cash_flow=trend_for(a, "operating_cash_flow", "Operating Cash Flow"),
        net_income=trend_for(a, "net_income", "Net Income"),
        gross_margin=margin_trend(a, "gross_profit", "Gross Margin"),
        operating_margin=margin_trend(a, "operating_income", "Operating Margin"),
        net_margin=margin_trend(a, "net_income", "Net Margin"),
    )
