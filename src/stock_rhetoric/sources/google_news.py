"""Google News RSS — aggregates Bloomberg / Reuters / WSJ / etc. (reliable tier)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import quote_plus

import aiohttp
import feedparser

from .base import SourceItem

_USER_AGENT = "stock-rhetoric/0.1"


def _parse(xml: str, limit: int) -> list[SourceItem]:
    feed = feedparser.parse(xml)
    items: list[SourceItem] = []
    for entry in feed.entries[:limit]:
        title = entry.get("title", "")
        link = entry.get("link", "")
        published = None
        if "published_parsed" in entry and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6])
            except Exception:
                published = None
        # Google News titles are typically "Headline - Source"
        publisher = ""
        if " - " in title:
            base, _, publisher = title.rpartition(" - ")
            title = base
        snippet = entry.get("summary", "")[:300]
        items.append(
            SourceItem(
                tier="reliable",
                source=f"Google News / {publisher}" if publisher else "Google News",
                title=title,
                snippet=snippet,
                url=link,
                published=published,
            )
        )
    return items


async def fetch(ticker: str, limit: int = 6, timeout: float = 8.0) -> list[SourceItem]:
    q = quote_plus(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                xml = await resp.text()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return []
    return await asyncio.to_thread(_parse, xml, limit)
