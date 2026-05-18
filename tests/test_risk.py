"""Risk flag detection."""

from stock_rhetoric import risk, trends


def _flags(fin):
    return risk.detect(fin, trends.analyze(fin), peers=None)


def test_strong_company_has_no_critical_flags(strong_company_financials):
    flags = _flags(strong_company_financials)
    high = [f for f in flags if f.severity == "high"]
    assert high == []


def test_weak_company_raises_multiple_flags(weak_company_financials):
    flags = _flags(weak_company_financials)
    names = {f.name for f in flags}
    # Critical conditions in the fixture:
    assert "Revenue contraction" in names
    assert "Weak liquidity" in names
    assert "Low interest coverage" in names
    assert "Negative operating cash flow" in names
    # And dilution from rising share count
    assert "Share dilution" in names
