"""Deterministic scoring smoke tests."""

from stock_rhetoric import scoring, trends


def _score(fin):
    return scoring.score(fin, trends.analyze(fin), peers=None)


def test_strong_company_scores_well(strong_company_financials):
    s = _score(strong_company_financials)
    assert s.overall is not None
    assert s.overall >= 65, f"expected ≥65 for a strong company, got {s.overall}"
    assert s.band in {"Healthy", "Strong"}
    cats = {c.name: c.score for c in s.categories}
    assert cats["Growth"] is not None and cats["Growth"] >= 70
    assert cats["Profitability"] is not None and cats["Profitability"] >= 70
    assert cats["Cash Flow Health"] is not None and cats["Cash Flow Health"] >= 60


def test_weak_company_scores_low(weak_company_financials):
    s = _score(weak_company_financials)
    assert s.overall is not None
    assert s.overall <= 50, f"expected ≤50 for a weak company, got {s.overall}"
    cats = {c.name: c.score for c in s.categories}
    assert cats["Growth"] is not None and cats["Growth"] <= 25
    assert cats["Financial Stability"] is not None and cats["Financial Stability"] <= 35


def test_overall_is_deterministic(strong_company_financials):
    a = _score(strong_company_financials)
    b = _score(strong_company_financials)
    assert a.overall == b.overall
    assert [c.score for c in a.categories] == [c.score for c in b.categories]


def test_linmap_and_tent():
    assert scoring.linmap(0.15, 0.0, 0.30) == 50.0
    assert scoring.linmap(-1.0, 0.0, 0.30) == 0.0
    assert scoring.linmap(99.0, 0.0, 0.30) == 100.0
    assert scoring.linmap_inverse(0.3, 0.3, 1.0) == 100.0
    assert scoring.tent(2.0, peak=2.0, half_width=1.0) == 100.0
    assert scoring.tent(3.0, peak=2.0, half_width=1.0) == 0.0
    assert scoring.tent(2.5, peak=2.0, half_width=1.0) == 50.0
