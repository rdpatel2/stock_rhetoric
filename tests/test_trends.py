"""Trend math."""

from stock_rhetoric import trends


def test_strong_company_revenue_trend(strong_company_financials):
    rep = trends.analyze(strong_company_financials)
    # 10B → 19B = +90% end-to-end, well past the 25% strong threshold.
    assert rep.revenue.direction == "up_strong"
    # YoY = 19/15.5 - 1 ≈ 22.6%
    assert rep.revenue.yoy is not None
    assert 0.20 < rep.revenue.yoy < 0.25
    # 3y CAGR from 10B → 19B over 3 years ≈ 23.8%
    assert rep.revenue.cagr_3y is not None
    assert 0.20 < rep.revenue.cagr_3y < 0.27


def test_weak_company_revenue_trend(weak_company_financials):
    rep = trends.analyze(weak_company_financials)
    # 6.0B → 5.1B = -15% end-to-end → down_slight (not strong, <25% magnitude).
    assert rep.revenue.direction == "down_slight"
    assert rep.revenue.yoy is not None
    assert rep.revenue.yoy < 0


def test_margin_trend_expansion(strong_company_financials):
    rep = trends.analyze(strong_company_financials)
    # Operating margin grew from 2.5/10=25% in 2020 to 6.1/19≈32% in 2023
    # → +28% relative move; lands in up_strong.
    assert rep.operating_margin.direction == "up_strong"


def test_margin_trend_compression(weak_company_financials):
    rep = trends.analyze(weak_company_financials)
    # Operating margin went from ~6.7% to ~-7.8% → sign flip, well past -25%.
    assert rep.operating_margin.direction == "down_strong"


def _bare_stat(series):
    """Run just the bucketing logic on a synthetic series."""
    return trends._direction(series)


def test_flat_series_returns_flat_code():
    # ~1.5% drift over the window, under the 2% flat band.
    assert _bare_stat([100.0, 100.5, 101.0, 101.5]) == "flat"


def test_slight_growth_band():
    # ~10% end-to-end growth — above flat (2%), below strong (25%).
    assert _bare_stat([100.0, 103.0, 106.0, 110.0]) == "up_slight"


def test_slight_decline_band():
    # ~10% end-to-end decline.
    assert _bare_stat([100.0, 97.0, 94.0, 90.0]) == "down_slight"


def test_strong_growth_band():
    assert _bare_stat([100.0, 130.0, 170.0, 210.0]) == "up_strong"
