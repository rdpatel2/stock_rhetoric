"""Reddit public .json endpoints — no auth, polite UA, rate-aware (social tier)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import aiohttp

from .base import SourceItem


_SUBS = ["stocks", "investing", "wallstreetbets"]
_USER_AGENT = "stock-rhetoric/0.1 (terminal research tool)"


async def _search_sub(session: aiohttp.ClientSession, sub: str, ticker: str, limit: int) -> list[SourceItem]:
    url = (
        f"https://www.reddit.com/r/{sub}/search.json"
        f"?q={ticker}&restrict_sr=1&sort=hot&t=week&limit={limit}"
    )
    try:
        async with session.get(url) as r:
            if r.status != 200:
                return []
            data = await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return []
    items: list[SourceItem] = []
    for child in (data.get("data") or {}).get("children", [])[:limit]:
        post = child.get("data") or {}
        title = post.get("title", "")
        if not title:
            continue
        url_ = "https://www.reddit.com" + post.get("permalink", "")
        ups = post.get("ups", 0)
        comments = post.get("num_comments", 0)
        body = (post.get("selftext") or "")[:200]
        ts = post.get("created_utc")
        published = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        items.append(
            SourceItem(
                tier="social",
                source=f"Reddit r/{sub}",
                title=title,
                snippet=f"{ups} ups, {comments} comments. {body}".strip(),
                url=url_,
                published=published,
            )
        )
    return items


async def fetch(ticker: str, per_sub: int = 3, timeout: float = 8.0) -> list[SourceItem]:
    headers = {"User-Agent": _USER_AGENT}
    try:
        async with aiohttp.ClientSession(
            headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as s:
            results = await asyncio.gather(
                *[_search_sub(s, sub, ticker, per_sub) for sub in _SUBS],
                return_exceptions=True,
            )
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return []
    out: list[SourceItem] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out
