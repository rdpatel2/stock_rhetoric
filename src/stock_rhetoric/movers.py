"""Top-N gainers for the current session (lightweight snapshots)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import yfinance as yf


@dataclass
class MoverSnapshot:
    ticker: str
    name: str
    price: Optional[float]
    change_pct: Optional[float]
    headline: Optional[str] = None


def _try_screen(limit: int) -> list[dict]:
    """Use yfinance's screener if available; return raw quote dicts."""
    # yfinance versions ≥ 0.2.40 expose `yf.screen` and `yf.PREDEFINED_SCREENER_BODIES`.
    try:
        body = yf.PREDEFINED_SCREENER_BODIES.get("day_gainers")  # type: ignore[attr-defined]
        if body is None:
            return []
        res = yf.screen(body, count=limit)  # type: ignore[attr-defined]
        return res.get("quotes", [])
    except Exception:
        pass
    # Older versions sometimes had `yf.screener`. Try that:
    try:
        s = yf.Screener()  # type: ignore[attr-defined]
        s.set_predefined_body("day_gainers")
        s.set_default_body(s.body)
        return (s.response or {}).get("quotes", [])
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
