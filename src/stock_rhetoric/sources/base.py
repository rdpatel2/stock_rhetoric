"""Shared SourceItem type for all sentiment sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SourceItem:
    tier: str            # "reliable" | "social"
    source: str          # human-friendly source name
    title: str
    snippet: str
    url: str
    published: Optional[datetime] = None
    sentiment_score: Optional[float] = None   # VADER compound, -1..+1
    sentiment_label: str = "neutral"           # "positive" | "neutral" | "negative"
