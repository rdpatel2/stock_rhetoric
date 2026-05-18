"""Shared fixtures."""

from __future__ import annotations

from datetime import date

import pytest

from stock_rhetoric.financials import (
    CompanyInfo,
    Financials,
    FinancialPeriod,
    KeyStats,
    PricePerformance,
)


def _period(year: int, **kw) -> FinancialPeriod:
    return FinancialPeriod(period_end=date(year, 12, 31), **kw)


@pytest.fixture
def strong_company_financials() -> Financials:
    """A fictional growing, profitable company with healthy balance sheet."""
    annual = [
        _period(
            2020,
            revenue=10_000_000_000, gross_profit=5_500_000_000,
            operating_income=2_500_000_000, ebitda=3_000_000_000,
            net_income=2_000_000_000, eps_diluted=2.0,
            interest_expense=200_000_000,
            total_assets=25_000_000_000, total_liabilities=10_000_000_000,
            total_equity=15_000_000_000, total_debt=5_000_000_000,
            current_assets=8_000_000_000, current_liabilities=4_000_000_000,
            operating_cash_flow=2_800_000_000, capex=-600_000_000,
            free_cash_flow=2_200_000_000,
            shares_outstanding=1_000_000_000,
        ),
        _period(
            2021,
            revenue=12_500_000_000, gross_profit=7_000_000_000,
            operating_income=3_500_000_000, ebitda=4_100_000_000,
            net_income=2_800_000_000, eps_diluted=2.8,
            interest_expense=180_000_000,
            total_assets=28_000_000_000, total_liabilities=10_500_000_000,
            total_equity=17_500_000_000, total_debt=5_000_000_000,
            current_assets=9_000_000_000, current_liabilities=4_200_000_000,
            operating_cash_flow=3_400_000_000, capex=-700_000_000,
            free_cash_flow=2_700_000_000,
            shares_outstanding=990_000_000,
        ),
        _period(
            2022,
            revenue=15_500_000_000, gross_profit=8_900_000_000,
            operating_income=4_700_000_000, ebitda=5_400_000_000,
            net_income=3_700_000_000, eps_diluted=3.75,
            interest_expense=170_000_000,
            total_assets=32_000_000_000, total_liabilities=11_000_000_000,
            total_equity=21_000_000_000, total_debt=4_800_000_000,
            current_assets=10_000_000_000, current_liabilities=4_400_000_000,
            operating_cash_flow=4_200_000_000, capex=-800_000_000,
            free_cash_flow=3_400_000_000,
            shares_outstanding=980_000_000,
        ),
        _period(
            2023,
            revenue=19_000_000_000, gross_profit=11_200_000_000,
            operating_income=6_100_000_000, ebitda=7_000_000_000,
            net_income=4_800_000_000, eps_diluted=4.95,
            interest_expense=160_000_000,
            total_assets=36_000_000_000, total_liabilities=11_500_000_000,
            total_equity=24_500_000_000, total_debt=4_500_000_000,
            current_assets=11_500_000_000, current_liabilities=4_500_000_000,
            operating_cash_flow=5_300_000_000, capex=-900_000_000,
            free_cash_flow=4_400_000_000,
            shares_outstanding=970_000_000,
        ),
    ]
    fin = Financials(
        company=CompanyInfo(
            ticker="STRONG", name="Strong Co.", sector="Technology",
            industry="Software—Application", exchange="NASDAQ",
            market_cap=120_000_000_000, enterprise_value=120_000_000_000,
        ),
        annual=annual,
        quarterly=[],
    )
    fin.price = PricePerformance(
        current=124.0, high_52w=130.0, low_52w=80.0,
        return_1m=0.05, return_3m=0.12, return_6m=0.20, return_1y=0.45, return_5y=2.0,
        volatility_annualized=0.30, beta=1.1,
    )
    fin.stats = KeyStats(
        pe=25.0, forward_pe=22.0, peg=1.2, ev_ebitda=17.0,
        price_to_sales=6.3, price_to_book=4.9, fcf_yield=0.037,
        roe=0.22, roa=0.14, roic=0.20,
        debt_to_equity=0.18, current_ratio=2.6, quick_ratio=1.8, interest_coverage=38.0,
        gross_margin=0.59, operating_margin=0.32, net_margin=0.25, ebitda_margin=0.37,
        asset_turnover=0.56,
        dividend_yield=0.012, payout_ratio=0.25, short_pct_float=0.02,
    )
    return fin


@pytest.fixture
def weak_company_financials() -> Financials:
    """A fictional struggling company — declining revenue, negative FCF, leveraged."""
    annual = [
        _period(
            2020, revenue=6_000_000_000, gross_profit=1_400_000_000,
            operating_income=400_000_000, ebitda=600_000_000,
            net_income=200_000_000, eps_diluted=0.5,
            interest_expense=300_000_000,
            total_assets=10_000_000_000, total_liabilities=8_000_000_000,
            total_equity=2_000_000_000, total_debt=6_000_000_000,
            current_assets=2_000_000_000, current_liabilities=2_500_000_000,
            operating_cash_flow=500_000_000, capex=-700_000_000,
            free_cash_flow=-200_000_000,
            shares_outstanding=400_000_000,
        ),
        _period(
            2021, revenue=5_700_000_000, gross_profit=1_200_000_000,
            operating_income=200_000_000, ebitda=400_000_000,
            net_income=50_000_000, eps_diluted=0.12,
            interest_expense=320_000_000,
            total_assets=10_500_000_000, total_liabilities=8_700_000_000,
            total_equity=1_800_000_000, total_debt=7_000_000_000,
            current_assets=1_900_000_000, current_liabilities=2_700_000_000,
            operating_cash_flow=300_000_000, capex=-700_000_000,
            free_cash_flow=-400_000_000,
            shares_outstanding=420_000_000,
        ),
        _period(
            2022, revenue=5_400_000_000, gross_profit=1_050_000_000,
            operating_income=-100_000_000, ebitda=200_000_000,
            net_income=-300_000_000, eps_diluted=-0.7,
            interest_expense=350_000_000,
            total_assets=10_800_000_000, total_liabilities=9_500_000_000,
            total_equity=1_300_000_000, total_debt=8_000_000_000,
            current_assets=1_700_000_000, current_liabilities=3_000_000_000,
            operating_cash_flow=100_000_000, capex=-700_000_000,
            free_cash_flow=-600_000_000,
            shares_outstanding=440_000_000,
        ),
        _period(
            2023, revenue=5_100_000_000, gross_profit=900_000_000,
            operating_income=-400_000_000, ebitda=-100_000_000,
            net_income=-700_000_000, eps_diluted=-1.5,
            interest_expense=400_000_000,
            total_assets=11_000_000_000, total_liabilities=10_500_000_000,
            total_equity=500_000_000, total_debt=9_500_000_000,
            current_assets=1_500_000_000, current_liabilities=3_200_000_000,
            operating_cash_flow=-100_000_000, capex=-700_000_000,
            free_cash_flow=-800_000_000,
            shares_outstanding=460_000_000,
        ),
    ]
    fin = Financials(
        company=CompanyInfo(
            ticker="WEAK", name="Weak Inc.", sector="Industrials",
            industry="Building Products & Equipment", exchange="NYSE",
            market_cap=2_500_000_000, enterprise_value=11_500_000_000,
        ),
        annual=annual,
        quarterly=[],
    )
    fin.price = PricePerformance(
        current=5.4, high_52w=14.0, low_52w=4.2, return_1y=-0.55,
        volatility_annualized=0.60, beta=1.8,
    )
    fin.stats = KeyStats(
        pe=None, forward_pe=None, peg=None, ev_ebitda=None,
        price_to_sales=0.5, price_to_book=5.0, fcf_yield=-0.32,
        roe=-1.4, roa=-0.06, roic=-0.04,
        debt_to_equity=19.0, current_ratio=0.47, quick_ratio=0.30, interest_coverage=-1.0,
        gross_margin=0.18, operating_margin=-0.08, net_margin=-0.14, ebitda_margin=-0.02,
        asset_turnover=0.47,
    )
    return fin
