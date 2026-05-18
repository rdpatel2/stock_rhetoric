"""Peer set selection and peer-relative metrics.

Yahoo / yfinance does not expose a stable "peers" endpoint, so we use a curated
industry → tickers mapping for the most common US industries. If the ticker's
industry isn't in the map, peer comparison is skipped and the report renders a
"peer data unavailable" note instead of failing.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from statistics import median
from typing import Optional

import yfinance as yf

from .financials import Financials


# A small but representative seed map. Industries below match yfinance's
# `info["industry"]` values (case-insensitive lookup).
_INDUSTRY_PEERS: dict[str, list[str]] = {
    "Semiconductors": ["NVDA", "AMD", "INTC", "AVGO", "TSM", "QCOM", "MU", "TXN"],
    "Software—Application": ["CRM", "ADBE", "INTU", "NOW", "WDAY", "TEAM", "DDOG"],
    "Software—Infrastructure": ["MSFT", "ORCL", "PANW", "SNPS", "CDNS", "FTNT", "CRWD"],
    "Internet Content & Information": ["GOOGL", "META", "PINS", "SNAP", "RDDT", "TTD"],
    "Internet Retail": ["AMZN", "BABA", "MELI", "EBAY", "ETSY", "SE"],
    "Consumer Electronics": ["AAPL", "SONY", "GPRO"],
    "Auto Manufacturers": ["TSLA", "F", "GM", "TM", "STLA", "RIVN", "LCID"],
    "Banks—Diversified": ["JPM", "BAC", "WFC", "C", "HSBC"],
    "Banks—Regional": ["USB", "PNC", "TFC", "MTB", "FITB", "RF"],
    "Credit Services": ["V", "MA", "AXP", "PYPL", "COF", "DFS"],
    "Drug Manufacturers—General": ["JNJ", "PFE", "MRK", "LLY", "ABBV", "BMY", "AZN"],
    "Biotechnology": ["AMGN", "GILD", "REGN", "VRTX", "MRNA", "BIIB"],
    "Medical Devices": ["MDT", "ABT", "BSX", "SYK", "EW", "ISRG"],
    "Oil & Gas Integrated": ["XOM", "CVX", "BP", "SHEL", "TTE"],
    "Aerospace & Defense": ["BA", "LMT", "RTX", "NOC", "GD", "TXT"],
    "Specialty Retail": ["HD", "LOW", "TJX", "ROST", "BBY", "ULTA"],
    "Restaurants": ["MCD", "SBUX", "CMG", "YUM", "DPZ", "QSR"],
    "Entertainment": ["DIS", "NFLX", "WBD", "PARA", "ROKU"],
    "Telecom Services": ["T", "VZ", "TMUS", "CHTR", "CMCSA"],
    "Utilities—Regulated Electric": ["NEE", "DUK", "SO", "AEP", "EXC", "XEL"],
    "Asset Management": ["BLK", "BX", "KKR", "APO", "ARES"],
    "REIT—Industrial": ["PLD", "DLR", "EQIX", "AMT", "PSA"],
    "Insurance—Diversified": ["BRK-B", "AIG", "MET", "PRU", "ALL"],
    "Airlines": ["DAL", "UAL", "AAL", "LUV", "ALK"],
    "Building Products & Equipment": ["CAT", "DE", "PCAR", "URI"],
    "Beverages—Non-Alcoholic": ["KO", "PEP", "MNST", "KDP"],
    "Household & Personal Products": ["PG", "CL", "KMB", "EL"],
    "Footwear & Accessories": ["NKE", "LULU", "DECK", "UA"],
}


# Metric attribute names on KeyStats that we'll aggregate to medians.
PEER_METRICS = [
    "pe",
    "forward_pe",
    "peg",
    "ev_ebitda",
    "price_to_sales",
    "price_to_book",
    "roe",
    "roa",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "debt_to_equity",
    "current_ratio",
    "dividend_yield",
]


@dataclass
class PeerSet:
    industry: Optional[str]
    tickers: list[str]
    medians: dict[str, Optional[float]]    # per-metric median across peers
    counts: dict[str, int]                 # how many peers contributed per metric


def peer_tickers_for(industry: Optional[str]) -> list[str]:
    if not industry:
        return []
    # Normalize: strip whitespace, case-insensitive
    key = industry.strip()
    if key in _INDUSTRY_PEERS:
        return list(_INDUSTRY_PEERS[key])
    # Fallback: case-insensitive lookup
    for k, v in _INDUSTRY_PEERS.items():
        if k.lower() == key.lower():
            return list(v)
    return []


def _peer_info_one(ticker: str) -> Optional[dict]:
    try:
        info = yf.Ticker(ticker).info
        return info if isinstance(info, dict) and info else None
    except Exception:
        return None


# Mapping from KeyStats attr → yfinance `info` key for peer fetch
_PEER_INFO_KEYS = {
    "pe": "trailingPE",
    "forward_pe": "forwardPE",
    "peg": "trailingPegRatio",
    "ev_ebitda": "enterpriseToEbitda",
    "price_to_sales": "priceToSalesTrailing12Months",
    "price_to_book": "priceToBook",
    "roe": "returnOnEquity",
    "roa": "returnOnAssets",
    "gross_margin": "grossMargins",
    "operating_margin": "operatingMargins",
    "net_margin": "profitMargins",
    "debt_to_equity": "debtToEquity",
    "current_ratio": "currentRatio",
    "dividend_yield": "dividendYield",
}


async def build_peer_set(fin: Financials, max_peers: int = 8) -> PeerSet:
    """Pick peers in the same industry and compute peer-medians for each ratio.

    Peer info fetches run in a thread pool so this remains within the per-ticker budget.
    Excludes the target ticker itself.
    """
    industry = fin.company.industry
    candidates = [t for t in peer_tickers_for(industry) if t.upper() != fin.company.ticker]
    candidates = candidates[:max_peers]
    if not candidates:
        return PeerSet(industry=industry, tickers=[], medians={k: None for k in PEER_METRICS}, counts={k: 0 for k in PEER_METRICS})

    infos = await asyncio.gather(*[asyncio.to_thread(_peer_info_one, t) for t in candidates])

    medians: dict[str, Optional[float]] = {}
    counts: dict[str, int] = {}
    for attr, key in _PEER_INFO_KEYS.items():
        vals: list[float] = []
        for info in infos:
            if not info:
                continue
            v = info.get(key)
            try:
                if v is None:
                    continue
                f = float(v)
                if f != f:  # NaN
                    continue
                # Normalize dividend yield: yfinance's dividendYield is in
                # percentage points (e.g., 0.36 means 0.36%). Convert to decimal.
                if attr == "dividend_yield":
                    f = f / 100.0
                vals.append(f)
            except (TypeError, ValueError):
                continue
        counts[attr] = len(vals)
        medians[attr] = median(vals) if vals else None

    return PeerSet(industry=industry, tickers=candidates, medians=medians, counts=counts)
