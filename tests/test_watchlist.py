"""Tests for watchlist storage, validation, and digest formatting.

Network calls are mocked — no real yfinance traffic.
"""

from __future__ import annotations

from datetime import date

import pytest

from stock_rhetoric import telegram_format, watchlist
from stock_rhetoric.watchlist import WatchQuote


@pytest.fixture(autouse=True)
def _isolate_watchlist(tmp_path, monkeypatch):
    """Point the watchlist file at a fresh tmp path for every test."""
    monkeypatch.setenv("STOCK_RHETORIC_WATCHLIST_PATH", str(tmp_path / "wl.json"))


@pytest.fixture
def _ok_validator(monkeypatch):
    monkeypatch.setattr(watchlist, "validate_ticker", lambda t: True)


def test_add_new_ticker(_ok_validator):
    status, norm = watchlist.add("u1", "aapl")
    assert (status, norm) == ("added", "AAPL")
    assert watchlist.get("u1") == ["AAPL"]


def test_add_duplicate_returns_duplicate(_ok_validator):
    watchlist.add("u1", "AAPL")
    status, norm = watchlist.add("u1", "AAPL")
    assert status == "duplicate"
    assert watchlist.get("u1") == ["AAPL"]


def test_add_invalid_format_short_circuits_before_network(monkeypatch):
    """Bad format must not even attempt validation."""
    called = {"n": 0}

    def boom(_):
        called["n"] += 1
        return True

    monkeypatch.setattr(watchlist, "validate_ticker", boom)
    status, _ = watchlist.add("u1", "123abc")
    assert status == "invalid"
    assert called["n"] == 0


def test_add_invalid_per_yfinance(monkeypatch):
    monkeypatch.setattr(watchlist, "validate_ticker", lambda t: False)
    status, norm = watchlist.add("u1", "ZZZZZZ")
    assert status == "invalid"
    assert norm == "ZZZZZZ"
    assert watchlist.get("u1") == []


def test_remove_existing(_ok_validator):
    watchlist.add("u1", "AAPL")
    status, norm = watchlist.remove("u1", "aapl")
    assert (status, norm) == ("removed", "AAPL")
    assert watchlist.get("u1") == []


def test_remove_missing(_ok_validator):
    status, norm = watchlist.remove("u1", "MSFT")
    assert status == "not_in_list"
    assert norm == "MSFT"


def test_remove_invalid_format():
    status, _ = watchlist.remove("u1", "not a ticker")
    assert status == "invalid"


def test_get_empty_user_returns_empty_list():
    assert watchlist.get("nobody") == []


def test_users_are_isolated(_ok_validator):
    watchlist.add("u1", "AAPL")
    watchlist.add("u2", "MSFT")
    assert watchlist.get("u1") == ["AAPL"]
    assert watchlist.get("u2") == ["MSFT"]


def test_persistence_across_loads(_ok_validator):
    watchlist.add("u1", "AAPL")
    watchlist.add("u1", "MSFT")
    # Second process would call load() fresh — simulate it.
    assert watchlist.load() == {"u1": ["AAPL", "MSFT"]}


def test_remove_last_ticker_drops_user_key(_ok_validator):
    watchlist.add("u1", "AAPL")
    watchlist.remove("u1", "AAPL")
    assert "u1" not in watchlist.load()


def test_load_handles_corrupt_file(tmp_path, monkeypatch):
    p = tmp_path / "wl.json"
    p.write_text("not json {{{")
    monkeypatch.setenv("STOCK_RHETORIC_WATCHLIST_PATH", str(p))
    assert watchlist.load() == {}


def test_validate_ticker_with_mocked_yfinance(monkeypatch):
    class FakeInfo:
        last_price = 123.45

    class FakeTicker:
        def __init__(self, _): pass
        @property
        def fast_info(self):
            return FakeInfo()

    monkeypatch.setattr(watchlist.yf, "Ticker", FakeTicker)
    assert watchlist.validate_ticker("AAPL") is True


def test_validate_ticker_returns_false_when_no_price(monkeypatch):
    class FakeInfo:
        last_price = None

    class FakeTicker:
        def __init__(self, _): pass
        @property
        def fast_info(self):
            return FakeInfo()

    monkeypatch.setattr(watchlist.yf, "Ticker", FakeTicker)
    assert watchlist.validate_ticker("ZZZZZZ") is False


def test_validate_ticker_returns_false_on_exception(monkeypatch):
    class FakeTicker:
        def __init__(self, _): raise RuntimeError("boom")

    monkeypatch.setattr(watchlist.yf, "Ticker", FakeTicker)
    assert watchlist.validate_ticker("AAPL") is False


# -------------------------------------------------------------------------------------
# Digest formatter
# -------------------------------------------------------------------------------------


def test_format_digest_open_shows_1w_change():
    quotes = [
        WatchQuote(
            ticker="AAPL", price=189.42, change_1d=0.012, change_1w=0.034,
            next_earnings=date(2026, 7, 25),
        ),
    ]
    text = telegram_format.format_digest("open", quotes)
    assert "market open" in text
    assert "1w change" in text
    assert "*AAPL*" in text
    assert "$189\\.42" in text          # MDv2 escapes the dot
    assert "\\+3\\.40%" in text         # 0.034 → +3.40%
    assert "2026\\-07\\-25" in text     # MDv2 escapes the hyphens


def test_format_digest_close_shows_1d_change():
    quotes = [
        WatchQuote(
            ticker="MSFT", price=412.0, change_1d=-0.005, change_1w=0.02,
            next_earnings=None,
        ),
    ]
    text = telegram_format.format_digest("close", quotes)
    assert "market close" in text
    assert "1d change" in text
    assert "*MSFT*" in text
    assert "↓" in text                  # negative change → down arrow
    assert "\\-0\\.50%" in text
    assert "earn" not in text           # no earnings date → no earn segment


def test_format_digest_empty_renders_placeholder():
    text = telegram_format.format_digest("open", [])
    assert "empty" in text.lower()


def test_format_digest_error_line():
    quotes = [WatchQuote(ticker="OOPS", error="no data")]
    text = telegram_format.format_digest("close", quotes)
    assert "*OOPS*" in text
    assert "no data" in text


# -------------------------------------------------------------------------------------
# Ack formatters
# -------------------------------------------------------------------------------------


def test_format_watchlist_ack_variants():
    assert "Tracking" in telegram_format.format_watchlist_ack("added", "AAPL", count=3)
    assert "Already" in telegram_format.format_watchlist_ack("duplicate", "AAPL")
    assert "isn't a valid" in telegram_format.format_watchlist_ack("invalid", "ZZZ")
    assert "Stopped" in telegram_format.format_watchlist_ack("removed", "AAPL")
    assert "isn't in your" in telegram_format.format_watchlist_ack("not_in_list", "AAPL")


def test_format_watchlist_list_empty_state():
    assert "empty" in telegram_format.format_watchlist_list([]).lower()


def test_format_watchlist_list_renders_tickers_and_prices():
    quotes = [
        WatchQuote(ticker="AAPL", price=189.42),
        WatchQuote(ticker="MSFT", price=412.00),
    ]
    text = telegram_format.format_watchlist_list(quotes)
    assert "AAPL" in text and "MSFT" in text
    assert "•" in text
    assert "$189\\.42" in text
    assert "$412\\.00" in text
    # Each ticker is wrapped in a MarkdownV2 link to Yahoo Finance.
    assert "[*AAPL*](https://finance.yahoo.com/quote/AAPL)" in text
    assert "[*MSFT*](https://finance.yahoo.com/quote/MSFT)" in text


def test_format_digest_ticker_is_yahoo_link():
    quotes = [WatchQuote(ticker="AAPL", price=189.42, change_1d=0.01, change_1w=0.02)]
    text = telegram_format.format_digest("close", quotes)
    assert "[*AAPL*](https://finance.yahoo.com/quote/AAPL)" in text


def test_format_watchlist_list_missing_price_falls_back_to_na():
    quotes = [WatchQuote(ticker="OOPS", price=None, error="no data")]
    text = telegram_format.format_watchlist_list(quotes)
    assert "OOPS" in text
    assert "n/a" in text
