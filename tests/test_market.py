"""NYSE open/closed checks."""

from datetime import date

from stock_rhetoric.market import check_nyse


def test_weekend_closed():
    # Saturday, May 16, 2026
    status = check_nyse(date(2026, 5, 16))
    assert status.is_open is False
    assert status.reason == "weekend"


def test_typical_weekday_open():
    # Wednesday, May 20, 2026 — not a US holiday
    status = check_nyse(date(2026, 5, 20))
    assert status.is_open is True
    assert status.reason == "open"


def test_christmas_closed():
    # Christmas Day 2025 was a Thursday — NYSE closed
    status = check_nyse(date(2025, 12, 25))
    assert status.is_open is False
    assert status.reason in {"holiday", "closed"}


def test_env_override(monkeypatch):
    monkeypatch.setenv("STOCK_RHETORIC_TODAY", "2026-05-16")
    status = check_nyse()
    assert status.as_of == date(2026, 5, 16)
    assert status.is_open is False
