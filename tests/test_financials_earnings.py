"""Tests for EarningsRecord rendering and earnings countdown in the header."""

from __future__ import annotations

from datetime import date, timedelta

from rich.console import Console

from stock_rhetoric.financials import EarningsRecord, Financials, CompanyInfo, PricePerformance, KeyStats
from stock_rhetoric.render import _earnings_table, _header_panel


def _minimal_fin(**overrides) -> Financials:
    fin = Financials(
        company=CompanyInfo(ticker="TEST", name="Test Corp"),
        price=PricePerformance(),
        stats=KeyStats(),
    )
    for k, v in overrides.items():
        setattr(fin, k, v)
    return fin


def _render(renderable) -> str:
    c = Console(record=True, width=120, highlight=False)
    c.print(renderable)
    return c.export_text()


# ---- EarningsRecord ----

def test_earnings_record_defaults():
    r = EarningsRecord()
    assert r.quarter is None
    assert r.eps_estimate is None
    assert r.eps_actual is None
    assert r.surprise_pct is None


def test_render_earnings_table_empty():
    fin = _minimal_fin(earnings_records=[])
    assert _earnings_table(fin) is None


def test_render_earnings_table_with_beat():
    records = [
        EarningsRecord(quarter=date(2024, 9, 30), eps_estimate=1.50, eps_actual=1.65, surprise_pct=10.0),
        EarningsRecord(quarter=date(2024, 6, 30), eps_estimate=1.40, eps_actual=1.35, surprise_pct=-3.6),
    ]
    fin = _minimal_fin(earnings_records=records)
    table = _earnings_table(fin)
    assert table is not None
    out = _render(table)
    assert "BEAT" in out
    assert "MISS" in out
    assert "Sep '24" in out
    assert "Jun '24" in out


def test_render_earnings_table_none_surprise():
    records = [EarningsRecord(quarter=date(2024, 3, 31))]
    fin = _minimal_fin(earnings_records=records)
    table = _earnings_table(fin)
    assert table is not None
    out = _render(table)
    assert "Mar '24" in out


# ---- Earnings countdown in header ----

def test_earnings_countdown_within_10_days():
    fin = _minimal_fin(next_earnings_date=date.today() + timedelta(days=5))
    out = _render(_header_panel(fin))
    assert "Earnings in 5d" in out


def test_earnings_countdown_zero_days():
    fin = _minimal_fin(next_earnings_date=date.today())
    out = _render(_header_panel(fin))
    assert "Earnings in 0d" in out


def test_earnings_date_no_countdown_beyond_10():
    fin = _minimal_fin(next_earnings_date=date.today() + timedelta(days=15))
    out = _render(_header_panel(fin))
    assert "Earnings in" not in out
    assert "Earnings:" in out


def test_ex_dividend_shown_in_header():
    fin = _minimal_fin(ex_dividend_date=date(2025, 8, 8))
    out = _render(_header_panel(fin))
    assert "Ex-Div" in out
    assert "Aug 08" in out


def test_no_dates_header_unchanged():
    fin = _minimal_fin()
    out = _render(_header_panel(fin))
    assert "Earnings" not in out
    assert "Ex-Div" not in out
