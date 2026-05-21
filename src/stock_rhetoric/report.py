"""End-to-end report assembly: fetch → analyze → score → narrate."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from . import aggregator, financials, finra as finra_mod, llm, peers, risk, scoring, trends


@dataclass
class Report:
    fin: financials.Financials
    trends: trends.TrendReport
    peers: Optional[peers.PeerSet]
    scorecard: scoring.Scorecard
    risk_flags: list[risk.RiskFlag]
    sentiment: aggregator.SentimentBundle
    narrative: llm.Narrative
    finra: Optional[finra_mod.FinraData] = None
    stage_timings: dict[str, float] = field(default_factory=dict)


async def build(
    ticker: str,
    *,
    with_llm: bool = True,
    deep_paragraphs: bool = False,
    source_timeout: float = 8.0,
    llm_timeout: float = 90.0,
    model: Optional[str] = None,
    on_stage: Optional[callable] = None,
) -> Report:
    """Pipeline (all stages have hard timeouts):
        - financials + sentiment in parallel
        - peer set (capped)
        - deterministic trends + scores + risk flags
        - LLM prose (hard timeout; falls back if slow)
    """
    timings: dict[str, float] = {}

    def _emit(stage: str):
        if on_stage:
            on_stage(stage)

    _emit("financials + sentiment + FINRA")
    t0 = time.monotonic()
    fin_future = asyncio.to_thread(financials.fetch, ticker)
    sent_future = aggregator.gather(ticker, per_source_timeout=source_timeout)

    async def _safe_finra() -> Optional[finra_mod.FinraData]:
        try:
            return await asyncio.wait_for(finra_mod.fetch(ticker), timeout=20.0)
        except Exception:
            return None

    fin, sentiment, finra_data = await asyncio.gather(
        fin_future, sent_future, _safe_finra()
    )
    timings["fetch"] = time.monotonic() - t0

    _emit("peer comparison")
    t0 = time.monotonic()
    try:
        peer_set = await asyncio.wait_for(peers.build_peer_set(fin), timeout=12.0)
    except asyncio.TimeoutError:
        peer_set = peers.PeerSet(industry=fin.company.industry, tickers=[], medians={}, counts={})
    timings["peers"] = time.monotonic() - t0

    t0 = time.monotonic()
    trend_report = trends.analyze(fin)
    scorecard = scoring.score(fin, trend_report, peer_set)
    flags = risk.detect(fin, trend_report, peer_set)
    timings["analytics"] = time.monotonic() - t0

    if with_llm:
        active_model = model or llm.DEFAULT_MODEL
        _emit(f"LLM narration · model={active_model} · loading…")
        t0 = time.monotonic()
        token_count = [0]

        def on_token(_tok: str) -> None:
            token_count[0] += 1
            if on_stage:
                elapsed = time.monotonic() - t0
                on_stage(f"LLM {active_model} · {token_count[0]} tokens · {elapsed:.0f}s")

        try:
            narrative = await asyncio.wait_for(
                asyncio.to_thread(
                    llm.narrate, fin, trend_report, peer_set, scorecard, flags, sentiment,
                    active_model, llm_timeout, deep_paragraphs, on_token,
                ),
                timeout=(llm_timeout * (2 if deep_paragraphs else 1)) + 5,
            )
        except asyncio.TimeoutError:
            narrative = llm.Narrative.empty(
                f"LLM timed out after {llm_timeout:.0f}s using model '{active_model}'. "
                "Try --no-llm, --model qwen2.5:1.5b, or raise OLLAMA_TIMEOUT_S."
            )
        timings["llm"] = time.monotonic() - t0
    else:
        narrative = llm.Narrative.empty("LLM disabled")

    return Report(
        fin=fin,
        trends=trend_report,
        peers=peer_set,
        scorecard=scorecard,
        risk_flags=flags,
        sentiment=sentiment,
        narrative=narrative,
        finra=finra_data,
        stage_timings=timings,
    )
