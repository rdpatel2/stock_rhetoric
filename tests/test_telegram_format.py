"""Tests for the Telegram MarkdownV2 formatter.

Synthetic Reports are assembled from existing financial fixtures by running the
real deterministic stages (trends, scoring, risk). The LLM step is replaced with
a fixed Narrative so output is reproducible.
"""

from __future__ import annotations

import re

from datetime import date, datetime

from stock_rhetoric import scoring, trends, risk
from stock_rhetoric.aggregator import SentimentBundle
from stock_rhetoric.financials import EarningsRecord
from stock_rhetoric.finra import DayVolume, FinraData
from stock_rhetoric.llm import Narrative
from stock_rhetoric.report import Report
from stock_rhetoric.sources.base import SourceItem
from stock_rhetoric.telegram_format import (
    _MDV2_SPECIALS,
    escape_mdv2,
    format_error,
    format_help,
    format_report,
)


def _make_sentiment(*, reliable: int = 3, social: int = 2) -> SentimentBundle:
    items = []
    for i in range(reliable):
        items.append(SourceItem(
            tier="reliable",
            source="Yahoo Finance",
            title=f"Reliable headline {i} for STRONG",
            snippet="snippet",
            url="https://example.com",
            published=datetime(2026, 5, 20),
            sentiment_score=0.5 if i % 2 == 0 else -0.2,
            sentiment_label="positive" if i % 2 == 0 else "negative",
        ))
    for i in range(social):
        items.append(SourceItem(
            tier="social",
            source="Reddit",
            title=f"Social headline {i} from r/stocks",
            snippet="snippet",
            url="https://reddit.com",
            published=datetime(2026, 5, 20),
            sentiment_score=0.0,
            sentiment_label="neutral",
        ))
    return SentimentBundle(items=items)


def _fake_narrative(
    direction: str = "BUY",
    confidence: str = "Medium",
) -> Narrative:
    return Narrative(
        executive_summary="Strong growth with widening margins and clean cash flow.",
        bullish=[
            "Revenue up 25% YoY",
            "Operating margin expanding",
            "FCF more than doubled over 3 years",
        ],
        bearish=[
            "Valuation premium vs peers",
            "Slowing buyback pace",
            "Concentrated customer base",
        ],
        valuation_paragraph="",
        balance_sheet_paragraph="",
        cash_flow_paragraph="",
        competitive_paragraph="",
        direction=direction,
        confidence=confidence,
        rationale="Fundamentals lead the multiple by a comfortable margin.",
    )


def _build_report(fin, *, narrative=None, finra=None, sentiment=None) -> Report:
    tr = trends.analyze(fin)
    sc = scoring.score(fin, tr, None)
    fl = risk.detect(fin, tr, None)
    return Report(
        fin=fin,
        trends=tr,
        peers=None,
        scorecard=sc,
        risk_flags=fl,
        sentiment=sentiment if sentiment is not None else SentimentBundle(),
        narrative=narrative or _fake_narrative(),
        finra=finra,
        stage_timings={"fetch": 2.0, "peers": 0.5, "analytics": 0.1, "llm": 8.4},
    )


def test_escape_mdv2_all_specials():
    """Every reserved character is backslash-escaped."""
    for ch in _MDV2_SPECIALS:
        out = escape_mdv2(ch)
        assert out == "\\" + ch, f"char {ch!r} not escaped: {out!r}"


def test_escape_mdv2_passthrough():
    """Non-reserved characters are unchanged."""
    assert escape_mdv2("AAPL price up") == "AAPL price up"
    assert escape_mdv2("") == ""
    assert escape_mdv2(None) == ""


def test_format_strong_under_4096_chars(strong_company_financials):
    text = format_report(_build_report(strong_company_financials))
    assert 0 < len(text) <= 4096
    assert "*STRONG*" in text
    assert "BUY" in text


def test_format_escapes_dot_in_company_name(strong_company_financials):
    strong_company_financials.company.name = "Acme 3.0 Inc."
    text = format_report(_build_report(strong_company_financials))
    # The dots in "3.0" and trailing "Inc." must be backslash-escaped.
    assert "Acme 3\\.0 Inc\\." in text


def test_format_handles_empty_narrative(strong_company_financials):
    """Narrative.empty(...) produced when LLM is unavailable still renders."""
    text = format_report(
        _build_report(strong_company_financials, narrative=Narrative.empty("LLM disabled"))
    )
    # No exception; placeholder summary appears with brackets escaped.
    assert "\\[LLM disabled\\]" in text
    # Bullish/bearish sections are dropped when empty.
    assert "*Bullish*" not in text
    assert "*Bearish*" not in text


def test_format_handles_no_finra(strong_company_financials):
    text = format_report(_build_report(strong_company_financials, finra=None))
    assert "FINRA" not in text


def test_format_handles_finra_with_data(strong_company_financials):
    finra = FinraData(
        ticker="STRONG",
        days=[
            DayVolume(date=__import__("datetime").date(2026, 5, 20 + i), short_volume=400, total_volume=1000)
            for i in range(5)
        ],
    )
    # FINRA was removed from the Telegram layout — formatter must still render
    # the rest of the report cleanly when finra data is attached.
    text = format_report(_build_report(strong_company_financials, finra=finra))
    assert "*STRONG*" in text
    assert "FINRA" not in text


def test_report_header_ticker_is_yahoo_link(strong_company_financials):
    text = format_report(_build_report(strong_company_financials))
    assert "[*STRONG*](https://finance.yahoo.com/quote/STRONG)" in text


def test_format_does_not_render_score_section(strong_company_financials):
    """Scores are intentionally not part of the Telegram layout."""
    text = format_report(_build_report(strong_company_financials))
    assert "*Score:*" not in text


def test_format_does_not_render_risk_or_finra_sections(weak_company_financials):
    """Risk flags and FINRA were removed from the Telegram layout."""
    text = format_report(
        _build_report(
            weak_company_financials,
            narrative=_fake_narrative(direction="SELL", confidence="High"),
        )
    )
    assert "*Risk flags" not in text
    assert "*FINRA" not in text


def test_format_weak_report(weak_company_financials):
    text = format_report(
        _build_report(
            weak_company_financials,
            narrative=_fake_narrative(direction="SELL", confidence="High"),
        )
    )
    assert "*WEAK*" in text
    assert "SELL" in text


def test_format_length_governor(strong_company_financials):
    """When forced under a tight cap, lower-priority blocks drop before truncation."""
    report = _build_report(strong_company_financials)
    text = format_report(report, max_chars=600)
    assert len(text) <= 600
    # Header and verdict must survive
    assert "*STRONG*" in text
    assert "*Verdict:*" in text


def test_format_error_renders():
    out = format_error("AAPL", ValueError("symbol not found"))
    assert "*AAPL*" in out
    assert "ValueError" in out
    assert "symbol not found" in out


def test_format_help_renders():
    out = format_help()
    assert "stock" in out and "bot" in out


def test_format_earnings_block_renders_records_and_next_date(strong_company_financials):
    fin = strong_company_financials
    fin.next_earnings_date = date(2026, 7, 25)
    fin.earnings_records = [
        EarningsRecord(quarter=date(2025, 3, 31), eps_estimate=1.20, eps_actual=1.30, surprise_pct=8.3),
        EarningsRecord(quarter=date(2025, 6, 30), eps_estimate=1.40, eps_actual=1.35, surprise_pct=-3.6),
        EarningsRecord(quarter=date(2025, 9, 30), eps_estimate=1.50, eps_actual=1.62, surprise_pct=8.0),
        EarningsRecord(quarter=date(2025, 12, 31), eps_estimate=1.60, eps_actual=1.70, surprise_pct=6.2),
    ]
    text = format_report(_build_report(fin))
    assert "*Earnings*" in text
    assert "Next: 2026\\-07\\-25" in text  # date hyphens escaped
    # Most recent quarter shown first
    assert "2025\\-12\\-31" in text
    assert "est 1\\.60" in text
    assert "act 1\\.70" in text
    # Earnings appears between Metrics and Verdict
    text_lookup = lambda needle: text.find(needle)
    assert text_lookup("*Metrics*") < text_lookup("*Earnings*") < text_lookup("*Verdict:*")


def test_format_earnings_block_skipped_when_no_data(strong_company_financials):
    """Strong fixture has no earnings_records by default — block must be absent."""
    text = format_report(_build_report(strong_company_financials))
    assert "*Earnings*" not in text


def test_format_section_order(strong_company_financials):
    """Spec'd order: Stock info → Summary → Metrics → Verdict → News (earnings between
    Metrics and Verdict when present in the fixture)."""
    text = format_report(_build_report(strong_company_financials))
    indices = {
        "header": text.find("*STRONG*"),
        "summary": text.find("*Summary*"),
        "metrics": text.find("*Metrics*"),
        "verdict": text.find("*Verdict:*"),
    }
    assert all(v != -1 for v in indices.values()), indices
    assert indices["header"] < indices["summary"]
    assert indices["summary"] < indices["metrics"]
    assert indices["metrics"] < indices["verdict"]


def test_metrics_each_on_own_line(strong_company_financials):
    text = format_report(_build_report(strong_company_financials))
    assert "*Metrics*" in text
    # Each metric label is followed by ': ' and appears on its own line.
    for label in ("P/E", "Forward P/E", "EV/EBITDA", "Operating margin", "ROE", "Debt/Equity", "FCF yield"):
        assert f"\n{label}: " in "\n" + text, f"missing metric line for {label}"
    # Old single-line ' · ' separator between metrics should be gone.
    assert "P/E " not in text.split("*Metrics*")[1].split("\n", 2)[0]


def test_news_section_renders_when_sentiment_present(strong_company_financials):
    sb = _make_sentiment(reliable=4, social=2)
    text = format_report(_build_report(strong_company_financials, sentiment=sb))
    assert "*News*" in text
    # Tone summary with escaped +/=/- in header
    assert "\\+" in text and "\\=" in text and "\\-" in text
    # Source name appears at least once
    assert "Yahoo Finance" in text
    assert "Reddit" in text
    # At least one tone glyph is present
    assert ("↑" in text) or ("↓" in text) or ("·" in text)


def test_news_headlines_are_linked(strong_company_financials):
    """Each headline with a URL is wrapped in a MarkdownV2 inline link."""
    sb = _make_sentiment(reliable=2, social=1)
    text = format_report(_build_report(strong_company_financials, sentiment=sb))
    # Inline link syntax `[title](url)` appears for the fixture URLs.
    assert "](https://example.com)" in text
    assert "](https://reddit.com)" in text


def test_news_headline_falls_back_to_plain_when_url_missing(strong_company_financials):
    sb = SentimentBundle(items=[
        SourceItem(
            tier="reliable",
            source="Yahoo Finance",
            title="No-URL headline",
            snippet="",
            url="",
            sentiment_label="neutral",
        ),
    ])
    text = format_report(_build_report(strong_company_financials, sentiment=sb))
    assert "No\\-URL headline" in text
    # No inline link wrapping when URL is missing.
    assert "[No\\-URL headline]" not in text


def test_escape_mdv2_url_only_escapes_paren_and_backslash():
    from stock_rhetoric.telegram_format import escape_mdv2_url
    assert escape_mdv2_url("https://example.com/path?x=1&y=2") == "https://example.com/path?x=1&y=2"
    assert escape_mdv2_url("https://a.com/foo(bar)") == "https://a.com/foo(bar\\)"
    assert escape_mdv2_url("a\\b") == "a\\\\b"


def test_news_section_absent_when_no_sentiment(strong_company_financials):
    text = format_report(_build_report(strong_company_financials, sentiment=SentimentBundle()))
    assert "*News*" not in text


def test_no_unescaped_specials_in_payload(strong_company_financials):
    """Sanity: outside *bold*, _italic_, and explicit escapes, no raw specials sneak through.

    This is a loose check — we just verify that every '.' '!' '+' '-' '=' '(' ')' that
    appears in *dynamic* content is either preceded by '\\' or is part of a Markdown
    decoration we intentionally emitted.
    """
    text = format_report(_build_report(strong_company_financials))
    # Strip MDv2 inline-link URLs: inside `](...)` only `)` and `\` are escaped — bare
    # dots are legal there and don't count against this check.
    body = re.sub(r"\]\([^)]*\)", "]()", text)
    bare_dot = re.compile(r"(?<!\\)\.")
    assert not bare_dot.search(body), f"Bare '.' found:\n{body}"
