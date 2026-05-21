"""Unit tests for finra.py z-score logic (no network calls)."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from stock_rhetoric.finra import DayVolume, FinraData, _DISPLAY_DAYS


def _day(offset: int, short_pct: float, total: int = 1_000_000) -> DayVolume:
    """Create a DayVolume `offset` days from a fixed anchor date."""
    return DayVolume(
        date=date(2025, 1, 2) + timedelta(days=offset),
        short_volume=int(short_pct * total),
        total_volume=total,
    )


def _baseline(n: int, pct: float) -> list[DayVolume]:
    """n days all at the same short_pct."""
    return [_day(i, pct) for i in range(n)]


class TestBaselineStats:
    def test_mean_uniform(self):
        fd = FinraData(ticker="X", days=_baseline(10, 0.50))
        assert fd.baseline_mean() == pytest.approx(0.50)

    def test_mean_mixed(self):
        days = [_day(0, 0.40), _day(1, 0.60)]
        assert FinraData(ticker="X", days=days).baseline_mean() == pytest.approx(0.50)

    def test_std_uniform_is_zero(self):
        fd = FinraData(ticker="X", days=_baseline(10, 0.50))
        assert fd.baseline_std() == pytest.approx(0.0)

    def test_std_known_value(self):
        # Two values: 0.40 and 0.60 → sample std = 0.1414...
        days = [_day(0, 0.40), _day(1, 0.60)]
        assert FinraData(ticker="X", days=days).baseline_std() == pytest.approx(math.sqrt(0.02), rel=1e-4)

    def test_mean_none_on_empty(self):
        assert FinraData(ticker="X").baseline_mean() is None

    def test_std_none_on_single_day(self):
        assert FinraData(ticker="X", days=[_day(0, 0.50)]).baseline_std() is None


class TestZScore:
    def _fd_with_spike(self, baseline_pct: float, spike_pct: float, n_baseline: int = 29) -> FinraData:
        """n_baseline days at baseline_pct, then one spike day."""
        days = _baseline(n_baseline, baseline_pct) + [_day(n_baseline, spike_pct)]
        return FinraData(ticker="X", days=days)

    def test_spike_above_baseline_is_positive(self):
        fd = self._fd_with_spike(0.50, 0.70)
        z = fd.day_z_score(fd._sorted()[-1])
        assert z is not None and z > 0

    def test_spike_below_baseline_is_negative(self):
        fd = self._fd_with_spike(0.50, 0.30)
        z = fd.day_z_score(fd._sorted()[-1])
        assert z is not None and z < 0

    def test_at_mean_is_near_zero(self):
        # A day exactly at the baseline mean should give z ≈ 0
        days = [_day(i, 0.40 if i % 2 == 0 else 0.60) for i in range(30)]
        fd = FinraData(ticker="X", days=days)
        mean_day = _day(30, fd.baseline_mean())
        z = fd.day_z_score(mean_day)
        assert z == pytest.approx(0.0, abs=0.01)

    def test_zero_std_returns_none(self):
        fd = FinraData(ticker="X", days=_baseline(10, 0.50))
        z = fd.day_z_score(_day(10, 0.50))
        assert z is None

    def test_no_days_returns_none(self):
        fd = FinraData(ticker="X")
        assert fd.day_z_score(_day(0, 0.50)) is None


class TestDayLabel:
    def _fd_clear_signal(self, spike_pct: float) -> FinraData:
        """28 days at 0.50, then the day under test."""
        days = _baseline(28, 0.50) + [_day(28, spike_pct)]
        return FinraData(ticker="X", days=days)

    def test_high_spike_is_bearish(self):
        fd = self._fd_clear_signal(0.80)
        assert fd.day_label(fd._sorted()[-1]) == "Bearish"

    def test_low_spike_is_bullish(self):
        fd = self._fd_clear_signal(0.20)
        assert fd.day_label(fd._sorted()[-1]) == "Bullish"

    def test_at_baseline_is_neutral(self):
        fd = self._fd_clear_signal(0.50)
        assert fd.day_label(fd._sorted()[-1]) == "Neutral"

    def test_zero_std_defaults_to_neutral(self):
        fd = FinraData(ticker="X", days=_baseline(10, 0.50))
        assert fd.day_label(_day(10, 0.90)) == "Neutral"


class TestDirectionalLabel:
    def test_bearish_when_recent_days_all_high(self):
        # 25 days at 50%, last 5 at 80% → avg z should be >> 1.5
        days = _baseline(25, 0.50) + [_day(25 + i, 0.80) for i in range(5)]
        assert FinraData(ticker="X", days=days).directional_label() == "Bearish"

    def test_bullish_when_recent_days_all_low(self):
        days = _baseline(25, 0.50) + [_day(25 + i, 0.20) for i in range(5)]
        assert FinraData(ticker="X", days=days).directional_label() == "Bullish"

    def test_neutral_when_recent_days_at_baseline(self):
        days = _baseline(30, 0.50)
        assert FinraData(ticker="X", days=days).directional_label() == "Neutral"

    def test_unknown_on_empty(self):
        assert FinraData(ticker="X").directional_label() == "Unknown"


class TestAvgZScore:
    def test_recent_above_baseline_positive(self):
        days = _baseline(25, 0.50) + [_day(25 + i, 0.75) for i in range(5)]
        fd = FinraData(ticker="X", days=days)
        avg = fd.avg_z_score()
        assert avg is not None and avg > 1.5

    def test_returns_none_on_empty(self):
        assert FinraData(ticker="X").avg_z_score() is None

    def test_returns_none_when_std_zero(self):
        assert FinraData(ticker="X", days=_baseline(10, 0.50)).avg_z_score() is None


class TestRecentDays:
    def test_returns_last_n(self):
        days = [_day(i, 0.50) for i in range(30)]
        fd = FinraData(ticker="X", days=days)
        recent = fd.recent_days()
        assert len(recent) == _DISPLAY_DAYS
        assert recent[-1].date == days[-1].date

    def test_ordering_is_oldest_first(self):
        days = [_day(i, 0.50) for i in range(30)]
        fd = FinraData(ticker="X", days=days)
        recent = fd.recent_days()
        assert recent == sorted(recent, key=lambda d: d.date)

    def test_fewer_days_than_display_returns_all(self):
        days = [_day(i, 0.50) for i in range(3)]
        assert len(FinraData(ticker="X", days=days).recent_days()) == 3


class TestFetchError:
    def test_error_set_when_insufficient_days(self):
        days = [_day(i, 0.50) for i in range(5)]
        fd = FinraData(ticker="X", days=days, fetch_error="Only 5 of 30 days retrieved")
        assert fd.fetch_error is not None

    def test_no_error_field_on_sufficient_days(self):
        days = [_day(i, 0.50) for i in range(30)]
        assert FinraData(ticker="X", days=days).fetch_error is None


class TestDayVolumeShortPct:
    def test_calculation(self):
        d = DayVolume(date=date(2025, 5, 16), short_volume=550_000, total_volume=1_000_000)
        assert d.short_pct == pytest.approx(0.55)

    def test_zero_total_volume_safe(self):
        d = DayVolume(date=date(2025, 5, 16), short_volume=0, total_volume=0)
        assert d.short_pct == 0.0
