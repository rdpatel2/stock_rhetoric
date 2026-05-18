"""SEC EDGAR recent filings (reliable tier).

EDGAR requires a descriptive User-Agent. The CIK lookup is cached on disk.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

from .base import SourceItem

_CACHE_DIR = Path.home() / ".cache" / "stock_rhetoric"
_CIK_CACHE = _CACHE_DIR / "cik_map.json"
_CIK_TTL = timedelta(days=7)


def _ua() -> str:
    return os.environ.get("SEC_EDGAR_UA", "stock-rhetoric contact@example.com")


async def _cik_map() -> dict[str, str]:
    """Load (or refresh) ticker → CIK mapping. Cached weekly."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _CIK_CACHE.exists():
        age = time.time() - _CIK_CACHE.stat().st_mtime
        if age < _CIK_TTL.total_seconds():
            try:
                return json.loads(_CIK_CACHE.read_text())
            except Exception:
                pass
    headers = {"User-Agent": _ua(), "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get("https://www.sec.gov/files/company_tickers.json", headers=headers) as r:
                if r.status != 200:
                    return {}
                data = await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return {}
    # data shape: { "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ... }
    out: dict[str, str] = {}
    for entry in data.values():
        cik = str(entry.get("cik_str", "")).zfill(10)
        ticker = entry.get("ticker", "").upper()
        if ticker and cik:
            out[ticker] = cik
    try:
        _CIK_CACHE.write_text(json.dumps(out))
    except Exception:
        pass
    return out


async def fetch(ticker: str, limit: int = 5, timeout: float = 8.0) -> list[SourceItem]:
    cik_map = await _cik_map()
    cik = cik_map.get(ticker.upper())
    if not cik:
        return []
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    headers = {"User-Agent": _ua(), "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.get(url, headers=headers) as r:
                if r.status != 200:
                    return []
                data = await r.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return []
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    company = data.get("name", ticker.upper())

    interesting = {"8-K", "10-K", "10-Q", "S-1", "S-3", "424B5", "DEF 14A"}
    items: list[SourceItem] = []
    for i, form in enumerate(forms):
        if form not in interesting:
            continue
        try:
            d = datetime.strptime(dates[i], "%Y-%m-%d")
        except (IndexError, ValueError):
            d = None
        acc = accessions[i].replace("-", "") if i < len(accessions) else ""
        doc = primary_docs[i] if i < len(primary_docs) else ""
        link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}" if acc and doc else ""
        items.append(
            SourceItem(
                tier="reliable",
                source="SEC EDGAR",
                title=f"{form} — {company}",
                snippet=f"Filing dated {dates[i] if i < len(dates) else ''}",
                url=link,
                published=d,
            )
        )
        if len(items) >= limit:
            break
    return items
