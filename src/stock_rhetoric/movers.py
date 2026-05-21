"""Top-N gainers for the current session (lightweight snapshots)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import yfinance as yf
from yahooquery import Screener

@dataclass
class MoverSnapshot:
    ticker: str
    name: str
    price: Optional[float]
    change_pct: Optional[float]
    headline: Optional[str] = None


def _try_screen(limit: int) -> list[dict]:
    """Use yfinance's screener if available; return raw quote dicts."""
    try:
        s = Screener()
        response = s.get_screeners("day_gainers").get("day_gainers")
        print(response.keys())
        return (response or {}).get("quotes", [])
    except Exception:
        return []


def _sync_top_gainers(limit: int) -> list[MoverSnapshot]:
    quotes = _try_screen(limit)
    snapshots: list[MoverSnapshot] = []
    for q in quotes[:limit]:
        snapshots.append(
            MoverSnapshot(
                ticker=q.get("symbol", ""),
                name=q.get("shortName") or q.get("longName") or q.get("symbol", ""),
                price=q.get("regularMarketPrice"),
                change_pct=q.get("regularMarketChangePercent"),
            )
        )
    # Best-effort: pull one headline per mover (in parallel via threads).
    def _headline(sym: str) -> Optional[str]:
        try:
            news = yf.Ticker(sym).news or []
            if not news:
                return None
            first = news[0]
            content = first.get("content") if isinstance(first, dict) else None
            if content:
                return content.get("title")
            return first.get("title")
        except Exception:
            return None

    for snap in snapshots:
        if snap.ticker:
            snap.headline = _headline(snap.ticker)
    return snapshots


async def top_gainers(limit: int = 5) -> list[MoverSnapshot]:
    return await asyncio.to_thread(_sync_top_gainers, limit)
