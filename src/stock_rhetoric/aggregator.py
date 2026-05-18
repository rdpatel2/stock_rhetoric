"""Run all sentiment sources in parallel and collect results.

Per-source hard timeout; one slow source must not block the report.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable

from . import sentiment as sentiment_mod
from .sources import google_news, reddit, sec_edgar, yfinance_news
from .sources.base import SourceItem


@dataclass
class SentimentBundle:
    items: list[SourceItem] = field(default_factory=list)
    failed_sources: list[str] = field(default_factory=list)

    @property
    def reliable(self) -> list[SourceItem]:
        return [i for i in self.items if i.tier == "reliable"]

    @property
    def social(self) -> list[SourceItem]:
        return [i for i in self.items if i.tier == "social"]

    def tone_summary(self) -> dict[str, float | int]:
        """Aggregate counts + net compound score across all items."""
        pos = sum(1 for i in self.items if i.sentiment_label == "positive")
        neg = sum(1 for i in self.items if i.sentiment_label == "negative")
        neu = sum(1 for i in self.items if i.sentiment_label == "neutral")
        scores = [i.sentiment_score for i in self.items if i.sentiment_score is not None]
        net = sum(scores) / len(scores) if scores else 0.0
        return {"positive": pos, "neutral": neu, "negative": neg, "net": round(net, 3)}


_SOURCES: list[tuple[str, Callable]] = [
    ("Yahoo Finance", yfinance_news.fetch),
    ("Google News", google_news.fetch),
    ("SEC EDGAR", sec_edgar.fetch),
    ("Reddit", reddit.fetch),
]


async def _run_one(name: str, fn: Callable, ticker: str, timeout: float) -> tuple[str, list[SourceItem] | None]:
    try:
        result = await asyncio.wait_for(fn(ticker), timeout=timeout)
        return name, result
    except (asyncio.TimeoutError, Exception):
        return name, None


async def gather(ticker: str, per_source_timeout: float = 8.0) -> SentimentBundle:
    tasks = [_run_one(name, fn, ticker, per_source_timeout) for name, fn in _SOURCES]
    results = await asyncio.gather(*tasks)
    bundle = SentimentBundle()
    for name, items in results:
        if items is None:
            bundle.failed_sources.append(name)
        else:
            bundle.items.extend(items)
    sentiment_mod.score_items(bundle.items)
    return bundle
