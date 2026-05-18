"""Headline sentiment scoring via VADER + a finance-specific lexicon overlay.

VADER is lexicon-based — sub-millisecond per headline, deterministic, no network.
The overlay teaches it the financial flavor of words like "beat / miss / downgrade /
guidance cut" that the stock lexicon misses or scores too weakly.
"""

from __future__ import annotations

from typing import Optional

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .sources.base import SourceItem


# Term → polarity score in VADER's -4..+4 scale. Tuned for short financial headlines.
FINANCE_LEXICON: dict[str, float] = {
    "beat": 2.0, "beats": 2.0, "beating": 2.0,
    "miss": -2.0, "misses": -2.0, "missed": -2.0,
    "upgrade": 1.8, "upgraded": 1.8, "upgrades": 1.8,
    "downgrade": -1.8, "downgraded": -1.8, "downgrades": -1.8,
    "outperform": 1.8, "outperforms": 1.8, "outperformed": 1.8,
    "underperform": -1.8, "underperforms": -1.8, "underperformed": -1.8,
    "bullish": 2.0, "bearish": -2.0,
    "rally": 1.5, "rallies": 1.5, "rallied": 1.5,
    "rout": -2.0, "routed": -2.0,
    "plunge": -2.5, "plunges": -2.5, "plunged": -2.5,
    "soar": 2.5, "soars": 2.5, "soared": 2.5,
    "tumble": -2.0, "tumbles": -2.0, "tumbled": -2.0,
    "surge": 2.0, "surges": 2.0, "surged": 2.0,
    "slump": -2.0, "slumps": -2.0, "slumped": -2.0,
    "lawsuit": -1.5, "probe": -1.5, "investigation": -1.2, "investigated": -1.2,
    "subpoena": -2.0, "fraud": -2.5,
    "layoffs": -1.8, "layoff": -1.8,
    "buyback": 1.2, "buybacks": 1.2,
    "dividend": 0.8,
    "raises": 1.2, "raised": 1.2,    # "raised guidance", "raises target"
    "cuts": -1.5, "cut": -1.5,        # "cuts guidance", "cut forecast"
    "halt": -1.5, "halted": -1.5,
    "recall": -1.5, "recalls": -1.5,
    "approval": 1.5, "approved": 1.5,
    "delays": -1.2, "delayed": -1.2,
    "warning": -1.5,
    "guidance": 0.3,   # neutral baseline; modified by surrounding raise/cut verbs
    "growth": 0.8,
    "loss": -1.5, "losses": -1.5,
    "profit": 1.2, "profits": 1.2, "profitable": 1.5,
    "record": 1.2,    # "record revenue", "record quarter"
    "all-time high": 1.8, "all time high": 1.8,
    "all-time low": -1.8, "all time low": -1.8,
}


_POS_THRESHOLD = 0.15
_NEG_THRESHOLD = -0.15


_analyzer: Optional[SentimentIntensityAnalyzer] = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    """Lazy singleton — VADER constructor reads its lexicon file from disk (~10 ms)."""
    global _analyzer
    if _analyzer is None:
        a = SentimentIntensityAnalyzer()
        a.lexicon.update(FINANCE_LEXICON)
        _analyzer = a
    return _analyzer


def score(text: str) -> tuple[float, str]:
    """Score a piece of text. Returns (compound, label).

    Label is "positive" / "negative" / "neutral" — tighter thresholds than VADER's
    default 0.05 so financial headlines that are mildly opinionated don't get
    over-classified.
    """
    if not text:
        return 0.0, "neutral"
    compound = _get_analyzer().polarity_scores(text)["compound"]
    if compound >= _POS_THRESHOLD:
        return compound, "positive"
    if compound <= _NEG_THRESHOLD:
        return compound, "negative"
    return compound, "neutral"


def score_items(items: list[SourceItem]) -> None:
    """Score each item in place. Uses title + snippet for a slightly richer signal."""
    for item in items:
        text = item.title
        if item.snippet:
            text = f"{text}. {item.snippet}"
        item.sentiment_score, item.sentiment_label = score(text)
