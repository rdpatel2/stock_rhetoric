"""FINRA RegSHO consolidated short-sale volume fetch (no auth required).

FINRA publishes a daily Consolidated NMS short-sale volume file covering
CBOE (B), NASDAQ (Q), and NYSE (N) markets as a single unified file.
URL: https://cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
Format: pipe-delimited — Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market
Volumes are fractional (retail programs trade fractional shares).

Signal logic: fetch 30 trading days, compute a per-stock rolling mean and std of
short%, then express the last 5 days as z-scores. ±1.5σ are the Bearish/Bullish
thresholds — stock-specific context rather than a market-wide absolute cut-off.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import aiohttp
import pandas_market_calendars as mcal

_CNMS_URL      = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{date}.txt"
_LOOKBACK_DAYS = 30    # trading days fetched for baseline
_DISPLAY_DAYS  = 5     # most-recent days used for the signal summary
_PER_FILE_TIMEOUT = aiohttp.ClientTimeout(total=10.0)
_HEADERS = {"User-Agent": "stock-rhetoric/0.1"}

_Z_BEARISH = 1.5    # z > +1.5σ → Bearish
_Z_BULLISH = -1.5   # z < -1.5σ → Bullish


@dataclass
class DayVolume:
    date: date
    short_volume: int
    total_volume: int

    @property
    def short_pct(self) -> float:
        return self.short_volume / self.total_volume if self.total_volume else 0.0


@dataclass
class FinraData:
    ticker: str
    days: list[DayVolume] = field(default_factory=list)   # oldest → newest
    fetch_error: Optional[str] = None

    def _sorted(self) -> list[DayVolume]:
        return sorted(self.days, key=lambda d: d.date)

    def recent_days(self, n: int = _DISPLAY_DAYS) -> list[DayVolume]:
        return self._sorted()[-n:]

    # ------------------------------------------------------------------
    # Baseline statistics (computed over all fetched days)
    # ------------------------------------------------------------------

    def baseline_mean(self) -> Optional[float]:
        if not self.days:
            return None
        pcts = [d.short_pct for d in self.days]
        return sum(pcts) / len(pcts)

    def baseline_std(self) -> Optional[float]:
        if len(self.days) < 2:
            return None
        pcts = [d.short_pct for d in self.days]
        mean = sum(pcts) / len(pcts)
        variance = sum((x - mean) ** 2 for x in pcts) / (len(pcts) - 1)
        return variance ** 0.5

    # ------------------------------------------------------------------
    # Z-score helpers
    # ------------------------------------------------------------------

    def day_z_score(self, day: DayVolume) -> Optional[float]:
        mean = self.baseline_mean()
        std = self.baseline_std()
        if mean is None or std is None or std == 0:
            return None
        return (day.short_pct - mean) / std

    def avg_z_score(self) -> Optional[float]:
        zs = [z for d in self.recent_days() if (z := self.day_z_score(d)) is not None]
        return sum(zs) / len(zs) if zs else None

    # ------------------------------------------------------------------
    # Signal labels
    # ------------------------------------------------------------------

    def day_label(self, day: DayVolume) -> str:
        z = self.day_z_score(day)
        if z is None:
            return "Neutral"
        if z > _Z_BEARISH:
            return "Bearish"
        if z < _Z_BULLISH:
            return "Bullish"
        return "Neutral"

    def directional_label(self) -> str:
        if not self.days:
            return "Unknown"
        avg_z = self.avg_z_score()
        if avg_z is None:
            return "Neutral"
        if avg_z > _Z_BEARISH:
            return "Bearish"
        if avg_z < _Z_BULLISH:
            return "Bullish"
        return "Neutral"


def _recent_trading_days(lookback: int) -> list[date]:
    """Return the last `lookback` completed NYSE trading days (oldest first)."""
    today = date.today()
    start = today - timedelta(days=lookback * 3 + 5)
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=start, end_date=today - timedelta(days=1))
    if schedule.empty:
        return []
    return [idx.date() for idx in schedule.index[-lookback:]]


async def _fetch_day(
    session: aiohttp.ClientSession,
    ticker: str,
    trade_date: date,
) -> Optional[DayVolume]:
    url = _CNMS_URL.format(date=trade_date.strftime("%Y%m%d"))
    upper_ticker = ticker.upper()
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            text = await resp.text(errors="replace")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("Date") or "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 5:
                    continue
                if parts[1].upper() != upper_ticker:
                    if parts[1] > upper_ticker:
                        break
                    continue
                try:
                    return DayVolume(
                        date=trade_date,
                        short_volume=int(float(parts[2])),
                        total_volume=int(float(parts[4])),
                    )
                except ValueError:
                    return None
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        pass
    return None


async def fetch(ticker: str, lookback: int = _LOOKBACK_DAYS) -> FinraData:
    trading_days = _recent_trading_days(lookback)
    if not trading_days:
        return FinraData(ticker=ticker, fetch_error="Could not determine recent trading days")

    connector = aiohttp.TCPConnector(limit=15)
    async with aiohttp.ClientSession(
        timeout=_PER_FILE_TIMEOUT, connector=connector, headers=_HEADERS
    ) as session:
        raw = await asyncio.gather(
            *[_fetch_day(session, ticker, td) for td in trading_days],
            return_exceptions=True,
        )

    results: list[DayVolume] = [r for r in raw if isinstance(r, DayVolume)]

    error: Optional[str] = None
    if len(results) < 10:
        error = f"Only {len(results)} of {lookback} days retrieved; z-score may be unreliable"

    return FinraData(ticker=ticker, days=results, fetch_error=error)
