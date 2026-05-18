"""Yahoo Finance news via yfinance (reliable tier)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import yfinance as yf

from .base import SourceItem


def _pull(ticker: str, limit: int) -> list[SourceItem]:
    items: list[SourceItem] = []
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return items
    for n in raw[:limit]:
        # yfinance v0.2.x: items can be in two shapes.
        # New shape: {"content": {"title", "summary", "pubDate", "canonicalUrl": {"url"}, "provider": {"displayName"}}}
        # Old shape: {"title", "publisher", "link", "providerPublishTime"}
        content = n.get("content") if isinstance(n, dict) else None
        if content:
            title = content.get("title") or ""
            snippet = (content.get("summary") or "")[:300]
            url = (content.get("canonicalUrl") or {}).get("url") or content.get("clickThroughUrl", {}).get("url", "")
            publisher = (content.get("provider") or {}).get("displayName") or "Yahoo Finance"
            ts = content.get("pubDate")
            try:
                published = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
            except Exception:
                published = None
        else:
            title = n.get("title", "")
            snippet = ""
            url = n.get("link", "")
            publisher = n.get("publisher", "Yahoo Finance")
            ts = n.get("providerPublishTime")
            published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        if not title:
            continue
        items.append(
            SourceItem(
                tier="reliable",
                source=f"Yahoo / {publisher}",
                title=title,
                snippet=snippet,
                url=url,
                published=published,
            )
        )
    return items


async def fetch(ticker: str, limit: int = 6) -> list[SourceItem]:
    return await asyncio.to_thread(_pull, ticker, limit)
