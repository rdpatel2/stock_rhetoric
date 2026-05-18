"""Aggregator: per-source timeout and partial-failure tolerance."""

import asyncio

import pytest

from stock_rhetoric import aggregator
from stock_rhetoric.sources.base import SourceItem


@pytest.fixture(autouse=True)
def patch_sources(monkeypatch):
    async def ok_reliable(_t):
        return [SourceItem(tier="reliable", source="Mock A", title="Headline A", snippet="", url="")]

    async def ok_social(_t):
        return [SourceItem(tier="social", source="Mock R", title="Reddit post", snippet="", url="")]

    async def slow(_t):
        await asyncio.sleep(5)
        return []

    async def boom(_t):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(aggregator, "_SOURCES", [
        ("MockA", ok_reliable),
        ("MockR", ok_social),
        ("Slow", slow),
        ("Boom", boom),
    ])


async def test_aggregator_returns_partial_on_failure():
    bundle = await aggregator.gather("AAPL", per_source_timeout=0.2)
    assert any(i.source == "Mock A" for i in bundle.items)
    assert any(i.source == "Mock R" for i in bundle.items)
    assert "Slow" in bundle.failed_sources
    assert "Boom" in bundle.failed_sources
    assert len(bundle.reliable) == 1
    assert len(bundle.social) == 1
