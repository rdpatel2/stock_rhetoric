"""Canonical yfinance data pull → normalized dataclasses.

Every downstream module (trends, scoring, risk, llm, render) consumes the `Financials`
object produced here. No other module re-fetches numeric data.

yfinance row labels have drifted across versions and across companies; the helpers
below tolerate aliases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pandas as pd
import yfinance as yf


# --------------------------------------------------------------------------------------
# Dataclasses
# --------------------------------------------------------------------------------------


@dataclass
class CompanyInfo:
    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    currency: str = "USD"
    business_summary: Optional[str] = None


@dataclass
class PricePerformance:
    current: Optional[float] = None
    high_52w: Optional[float] = None
    low_52w: Optional[float] = None
    change_today_pct: Optional[float] = None
    return_1d: Optional[float] = None
    return_1w: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_1y: Optional[float] = None
    return_5y: Optional[float] = None
    volatility_annualized: Optional[float] = None
    beta: Optional[float] = None


@dataclass
class KeyStats:
    pe: Optional[float] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    ev_ebitda: Optional[float] = None
    price_to_sales: Optional[float] = None
    price_to_book: Optional[float] = None
    fcf_yield: Optional[float] = None
    roe: Optional[float] = None
    roa: Optional[float] = None
    roic: Optional[float] = None
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    ebitda_margin: Optional[float] = None
    asset_turnover: Optional[float] = None
    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None
    short_pct_float: Optional[float] = None
    r_and_d_pct: Optional[float] = None


@dataclass
class FinancialPeriod:
    period_end: date
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    ebitda: Optional[float] = None
    net_income: Optional[float] = None
    eps_basic: Optional[float] = None
    eps_diluted: Optional[float] = None
    interest_expense: Optional[float] = None
    research_development: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    total_debt: Optional[float] = None
    long_term_debt: Optional[float] = None
    short_term_debt: Optional[float] = None
    cash: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    inventory: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None
    shares_outstanding: Optional[float] = None


@dataclass
class EarningsRecord:
    quarter: Optional[date] = None
    eps_estimate: Optional[float] = None
    eps_actual: Optional[float] = None
    surprise_pct: Optional[float] = None  # percentage points: 5.2 means +5.2%


@dataclass
class Financials:
    company: CompanyInfo
    price: PricePerformance = field(default_factory=PricePerformance)
    stats: KeyStats = field(default_factory=KeyStats)
    annual: list[FinancialPeriod] = field(default_factory=list)      # oldest → newest
    quarterly: list[FinancialPeriod] = field(default_factory=list)   # oldest → newest
    insiders_net_shares_6m: Optional[float] = None
    institutional_ownership_pct: Optional[float] = None
    analyst_mean_target: Optional[float] = None
    analyst_recommendation: Optional[str] = None
    earnings_surprises_pct: list[float] = field(default_factory=list)
    earnings_records: list[EarningsRecord] = field(default_factory=list)
    next_earnings_date: Optional[date] = None
    ex_dividend_date: Optional[date] = None
    top_institutional_holders: list[dict] = field(default_factory=list)
    raw_info: dict = field(default_factory=dict)  # original yfinance info (debugging)


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------


# yfinance / Yahoo statement row labels have multiple aliases. Each row in the
# DataFrame can appear under any of these names depending on the company/version.
_INCOME_ALIASES = {
    "revenue": ["Total Revenue", "Revenue", "TotalRevenue"],
    "gross_profit": ["Gross Profit", "GrossProfit"],
    "operating_income": ["Operating Income", "OperatingIncome"],
    "ebitda": ["EBITDA", "Normalized EBITDA", "NormalizedEBITDA"],
    "net_income": [
        "Net Income",
        "NetIncome",
        "Net Income Common Stockholders",
        "NetIncomeCommonStockholders",
    ],
    "eps_basic": ["Basic EPS", "BasicEPS"],
    "eps_diluted": ["Diluted EPS", "DilutedEPS"],
    "interest_expense": ["Interest Expense", "InterestExpense"],
    "research_development": [
        "Research And Development",
        "ResearchAndDevelopment",
        "Research Development",
        "Research and Development",
    ],
}
_BALANCE_ALIASES = {
    "total_assets": ["Total Assets", "TotalAssets"],
    "total_liabilities": [
        "Total Liabilities Net Minority Interest",
        "TotalLiabilitiesNetMinorityInterest",
        "Total Liab",
    ],
    "total_equity": [
        "Stockholders Equity",
        "StockholdersEquity",
        "Total Equity Gross Minority Interest",
    ],
    "total_debt": ["Total Debt", "TotalDebt"],
    "long_term_debt": ["Long Term Debt", "LongTermDebt"],
    "short_term_debt": ["Current Debt", "CurrentDebt", "Short Long Term Debt"],
    "cash": [
        "Cash And Cash Equivalents",
        "CashAndCashEquivalents",
        "Cash Cash Equivalents And Short Term Investments",
    ],
    "current_assets": ["Current Assets", "CurrentAssets"],
    "current_liabilities": ["Current Liabilities", "CurrentLiabilities"],
    "inventory": ["Inventory"],
}
_CASHFLOW_ALIASES = {
    "operating_cash_flow": [
        "Operating Cash Flow",
        "OperatingCashFlow",
        "Total Cash From Operating Activities",
    ],
    "capex": [
        "Capital Expenditure",
        "CapitalExpenditure",
        "Capital Expenditures",
    ],
    "free_cash_flow": ["Free Cash Flow", "FreeCashFlow"],
}


def _lookup(df: pd.DataFrame, aliases: list[str]) -> Optional[pd.Series]:
    """Return the first matching row from a yfinance financial DataFrame, or None."""
    if df is None or df.empty:
        return None
    for name in aliases:
        if name in df.index:
            return df.loc[name]
    return None


def _periods_from_statements(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
) -> list[FinancialPeriod]:
    """Merge income / balance / cashflow DataFrames into FinancialPeriod rows.

    yfinance returns these with columns = period-end timestamps (newest first).
    We unify the column set across all three, then build one row per period (oldest first).
    """
    cols: set = set()
    for df in (income, balance, cashflow):
        if df is not None and not df.empty:
            cols.update(df.columns)

    def _coerce_date(c) -> date:
        if isinstance(c, pd.Timestamp):
            return c.date()
        if isinstance(c, datetime):
            return c.date()
        if isinstance(c, date):
            return c
        return pd.Timestamp(c).date()

    sorted_cols = sorted(cols, key=lambda c: pd.Timestamp(c))

    def _val(df, aliases, col) -> Optional[float]:
        s = _lookup(df, aliases)
        if s is None or col not in s.index:
            return None
        v = s[col]
        if pd.isna(v):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    periods: list[FinancialPeriod] = []
    for c in sorted_cols:
        period = FinancialPeriod(period_end=_coerce_date(c))
        for field_name, aliases in _INCOME_ALIASES.items():
            setattr(period, field_name, _val(income, aliases, c))
        for field_name, aliases in _BALANCE_ALIASES.items():
            setattr(period, field_name, _val(balance, aliases, c))
        for field_name, aliases in _CASHFLOW_ALIASES.items():
            setattr(period, field_name, _val(cashflow, aliases, c))
        # FCF fallback: OCF + capex (capex is reported negative by yfinance).
        if period.free_cash_flow is None and period.operating_cash_flow is not None:
            if period.capex is not None:
                period.free_cash_flow = period.operating_cash_flow + period.capex
        periods.append(period)
    return periods


def _price_performance(t: yf.Ticker, info: dict) -> PricePerformance:
    pp = PricePerformance(beta=info.get("beta"))
    try:
        hist = t.history(period="5y", auto_adjust=True)
    except Exception:
        hist = pd.DataFrame()
    if hist.empty:
        return pp
    closes = hist["Close"].dropna()
    if closes.empty:
        return pp
    last = float(closes.iloc[-1])
    pp.current = info.get("currentPrice") or last
    pp.high_52w = info.get("fiftyTwoWeekHigh") or float(closes.tail(252).max())
    pp.low_52w = info.get("fiftyTwoWeekLow") or float(closes.tail(252).min())

    def _ret(days: int) -> Optional[float]:
        if len(closes) <= days:
            return None
        return float(last / closes.iloc[-days - 1] - 1)
    pp.return_1d = _ret(1)
    pp.return_1w = _ret(5)
    pp.return_1m = _ret(21)
    pp.return_3m = _ret(63)
    pp.return_6m = _ret(126)
    pp.return_1y = _ret(252)
    if len(closes) > 1:
        pp.return_5y = float(last / closes.iloc[0] - 1)

    daily_returns = closes.pct_change().dropna()
    if not daily_returns.empty:
        pp.volatility_annualized = float(daily_returns.std() * (252**0.5))

    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        pp.change_today_pct = (last / prev - 1) if prev else None
    return pp


def _dividend_yield(info: dict) -> Optional[float]:
    """Return dividend yield as a decimal fraction (0.005 = 0.5%).

    yfinance's `dividendYield` is in percentage points (0.36 means 0.36%).
    `trailingAnnualDividendYield` is in decimal form. Prefer the decimal field;
    if absent, fall back to dividendRate / currentPrice.
    """
    decimal_yield = info.get("trailingAnnualDividendYield")
    if decimal_yield is not None:
        return decimal_yield
    rate = info.get("dividendRate")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if rate and price:
        return rate / price
    # Last resort: assume yfinance returned percentage points.
    pp = info.get("dividendYield")
    return pp / 100.0 if pp is not None else None


def _key_stats(info: dict, annual: list[FinancialPeriod]) -> KeyStats:
    s = KeyStats(
        pe=info.get("trailingPE"),
        forward_pe=info.get("forwardPE"),
        peg=info.get("trailingPegRatio") or info.get("pegRatio"),
        price_to_sales=info.get("priceToSalesTrailing12Months"),
        price_to_book=info.get("priceToBook"),
        roe=info.get("returnOnEquity"),
        roa=info.get("returnOnAssets"),
        debt_to_equity=info.get("debtToEquity"),
        current_ratio=info.get("currentRatio"),
        quick_ratio=info.get("quickRatio"),
        gross_margin=info.get("grossMargins"),
        operating_margin=info.get("operatingMargins"),
        net_margin=info.get("profitMargins"),
        ebitda_margin=info.get("ebitdaMargins"),
        dividend_yield=_dividend_yield(info),
        payout_ratio=info.get("payoutRatio"),
        short_pct_float=info.get("shortPercentOfFloat"),
    )
    # EV / EBITDA
    ev = info.get("enterpriseValue")
    if ev and annual:
        latest = annual[-1]
        if latest.ebitda and latest.ebitda > 0:
            s.ev_ebitda = ev / latest.ebitda
    # FCF yield = FCF / market cap
    mcap = info.get("marketCap")
    if mcap and annual:
        latest = annual[-1]
        if latest.free_cash_flow:
            s.fcf_yield = latest.free_cash_flow / mcap
    # Interest coverage = operating income / interest expense (positive expense)
    if annual:
        latest = annual[-1]
        if latest.operating_income and latest.interest_expense:
            ie = abs(latest.interest_expense)
            if ie > 0:
                s.interest_coverage = latest.operating_income / ie
    # Asset turnover = revenue / avg total assets
    if len(annual) >= 2 and annual[-1].revenue and annual[-1].total_assets and annual[-2].total_assets:
        avg_assets = (annual[-1].total_assets + annual[-2].total_assets) / 2
        if avg_assets:
            s.asset_turnover = annual[-1].revenue / avg_assets
    # ROIC ≈ NOPAT / invested capital. Approximate: operating_income * (1-0.21) / (debt + equity)
    if annual:
        latest = annual[-1]
        if latest.operating_income and latest.total_equity:
            invested = (latest.total_equity or 0) + (latest.total_debt or 0)
            if invested > 0:
                s.roic = latest.operating_income * (1 - 0.21) / invested
    # R&D as % of revenue
    if annual:
        latest = annual[-1]
        if latest.research_development and latest.revenue:
            s.r_and_d_pct = latest.research_development / latest.revenue
    return s


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def fetch(ticker: str) -> Financials:
    """Pull and normalize all numeric data for `ticker` from yfinance."""
    t = yf.Ticker(ticker)
    info: dict = _safe(lambda: t.info, {}) or {}

    company = CompanyInfo(
        ticker=ticker.upper(),
        name=info.get("longName") or info.get("shortName") or ticker.upper(),
        sector=info.get("sector"),
        industry=info.get("industry"),
        exchange=info.get("fullExchangeName") or info.get("exchange"),
        market_cap=info.get("marketCap"),
        enterprise_value=info.get("enterpriseValue"),
        currency=info.get("currency", "USD"),
        business_summary=info.get("longBusinessSummary"),
    )

    annual = _periods_from_statements(
        _safe(lambda: t.financials, pd.DataFrame()),
        _safe(lambda: t.balance_sheet, pd.DataFrame()),
        _safe(lambda: t.cashflow, pd.DataFrame()),
    )
    quarterly = _periods_from_statements(
        _safe(lambda: t.quarterly_financials, pd.DataFrame()),
        _safe(lambda: t.quarterly_balance_sheet, pd.DataFrame()),
        _safe(lambda: t.quarterly_cashflow, pd.DataFrame()),
    )

    # Backfill shares outstanding (from info; per-period not always available).
    so = info.get("sharesOutstanding")
    if so:
        for p in annual + quarterly:
            if p.shares_outstanding is None:
                p.shares_outstanding = float(so)

    fin = Financials(
        company=company,
        annual=annual,
        quarterly=quarterly,
        raw_info=info,
    )
    fin.price = _price_performance(t, info)
    fin.stats = _key_stats(info, annual)

    # Next earnings date + ex-dividend date from the calendar
    try:
        cal = t.calendar
        if isinstance(cal, pd.DataFrame) and not cal.empty:
            # Newer yfinance returns a DataFrame; collapse first column to dict.
            cal = {str(k): v for k, v in cal.iloc[:, 0].items()}
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if isinstance(ed, (list, tuple)) and ed:
                fin.next_earnings_date = pd.Timestamp(ed[0]).date()
            elif ed is not None:
                fin.next_earnings_date = pd.Timestamp(ed).date()
            dd = cal.get("Ex-Dividend Date") or cal.get("Dividend Date")
            if dd is not None:
                fin.ex_dividend_date = pd.Timestamp(dd).date()
    except Exception:
        pass

    # Top institutional holders
    try:
        ih = t.institutional_holders
        if isinstance(ih, pd.DataFrame) and not ih.empty:
            for _, row in ih.head(5).iterrows():
                name = str(row.get("Holder") or row.get("holder") or "")
                pct = float(row.get("% Out") or row.get("pctHeld") or 0)
                shares = int(row.get("Shares") or row.get("shares") or 0)
                if name:
                    fin.top_institutional_holders.append({"name": name, "pct": pct, "shares": shares})
    except Exception:
        pass

    # Insider net shares (last 6 months — yfinance returns a DataFrame)
    try:
        ins = t.insider_transactions
        if isinstance(ins, pd.DataFrame) and not ins.empty:
            # Many yfinance versions have columns "Shares" and "Transaction" (Buy/Sell).
            if "Shares" in ins.columns and "Transaction" in ins.columns:
                buys = ins[ins["Transaction"].str.contains("Buy", case=False, na=False)][
                    "Shares"
                ].sum()
                sells = ins[ins["Transaction"].str.contains("Sale", case=False, na=False)][
                    "Shares"
                ].sum()
                fin.insiders_net_shares_6m = float(buys - sells)
    except Exception:
        pass

    fin.institutional_ownership_pct = info.get("heldPercentInstitutions")
    fin.analyst_mean_target = info.get("targetMeanPrice")
    fin.analyst_recommendation = info.get("recommendationKey")

    # Earnings history: surprise % list + per-quarter records for the table
    try:
        eh = t.earnings_history
        if isinstance(eh, pd.DataFrame) and not eh.empty:
            if "surprisePercent" in eh.columns:
                fin.earnings_surprises_pct = [
                    float(v) for v in eh["surprisePercent"].dropna().tail(4).tolist()
                ]
            records = []
            for idx, row in eh.tail(4).iterrows():
                try:
                    q = pd.Timestamp(idx).date()
                except Exception:
                    q = None

                def _ef(v):
                    try:
                        return float(v) if v is not None and not pd.isna(v) else None
                    except Exception:
                        return None

                records.append(EarningsRecord(
                    quarter=q,
                    eps_estimate=_ef(row.get("epsEstimate")),
                    eps_actual=_ef(row.get("epsActual")),
                    surprise_pct=_ef(row.get("surprisePercent")),
                ))
            fin.earnings_records = records
    except Exception:
        pass

    return fin
