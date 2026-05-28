"""LLM wrapper: mocks Ollama streaming + checks plain-text parsing + fallback."""

from stock_rhetoric import aggregator, llm, peers, risk, scoring, trends


def _full_context(fin):
    tr = trends.analyze(fin)
    ps = peers.PeerSet(industry=fin.company.industry, tickers=[], medians={}, counts={})
    sc = scoring.score(fin, tr, ps)
    flags = risk.detect(fin, tr, ps)
    sentiment = aggregator.SentimentBundle()
    return tr, ps, sc, flags, sentiment


class _MockMessage:
    def __init__(self, content: str):
        self.content = content


class _MockChunk:
    """Mimics ollama.ChatResponse: has a `.message.content` attribute."""
    def __init__(self, content: str):
        self.message = _MockMessage(content)


def _streaming_response(text: str):
    """Yield one Ollama-shaped chunk per token of `text` (Pydantic-model style)."""
    for ch in text:
        yield _MockChunk(ch)


def test_narrate_returns_empty_on_ollama_error(monkeypatch, strong_company_financials):
    class FailingClient:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k):
            raise ConnectionError("ollama down")

    monkeypatch.setattr(llm.ollama, "Client", FailingClient)
    tr, ps, sc, flags, sent = _full_context(strong_company_financials)
    nar = llm.narrate(strong_company_financials, tr, ps, sc, flags, sent)
    assert "LLM error" in nar.executive_summary or "LLM error" in nar.rationale
    assert nar.direction in {"BUY", "HOLD", "SELL"}


def test_narrate_parses_structured_text(monkeypatch, strong_company_financials):
    text = (
        "SUMMARY: Solid growth across margins and FCF.\n"
        "BULL: Margins expanding\n"
        "BULL: FCF strong\n"
        "BEAR: Valuation rich\n"
        "DIRECTION: BUY\n"
        "CONFIDENCE: Medium\n"
        "RATIONALE: Fundamentals and growth justify a buy.\n"
    )

    class OkClient:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k):
            assert k.get("stream") is True
            return _streaming_response(text)

    monkeypatch.setattr(llm.ollama, "Client", OkClient)
    tr, ps, sc, flags, sent = _full_context(strong_company_financials)
    nar = llm.narrate(strong_company_financials, tr, ps, sc, flags, sent)
    assert nar.direction == "BUY"
    assert nar.confidence == "Medium"
    assert "Solid growth" in nar.executive_summary
    assert len(nar.bullish) == 2
    assert len(nar.bearish) == 1


def test_parser_handles_markdown_and_case(monkeypatch, strong_company_financials):
    """Small models often output markdown / mixed case. The lenient parser must handle it."""
    text = (
        "**Executive Summary**: Solid growth across margins and FCF.\n"
        "## Bullish:\n"
        "- Margins expanding\n"
        "* Bull: FCF strong\n"   # alt key style
        "Bearish:\n"
        "1. Bear: Valuation rich\n"
        "Direction — BUY\n"   # em dash instead of colon
        "Confidence: medium\n"
        "Rationale: Fundamentals justify a buy.\n"
    )

    class OkClient:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k):
            return _streaming_response(text)

    monkeypatch.setattr(llm.ollama, "Client", OkClient)
    tr, ps, sc, flags, sent = _full_context(strong_company_financials)
    nar = llm.narrate(strong_company_financials, tr, ps, sc, flags, sent)
    assert nar.direction == "BUY"
    assert nar.confidence == "Medium"
    assert "Solid growth" in nar.executive_summary
    assert any("FCF" in b for b in nar.bullish)
    assert any("Valuation" in b for b in nar.bearish)


def test_parser_falls_back_to_json(monkeypatch, strong_company_financials):
    """If the model emits JSON despite the prompt, we should still parse it."""
    text = (
        "Sure, here's the analysis:\n"
        '{"executive_summary": "Solid.", "bullish": ["x","y"], "bearish": ["z"],'
        ' "direction": "BUY", "confidence": "High", "rationale": "ok"}\n'
    )

    class OkClient:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k):
            return _streaming_response(text)

    monkeypatch.setattr(llm.ollama, "Client", OkClient)
    tr, ps, sc, flags, sent = _full_context(strong_company_financials)
    nar = llm.narrate(strong_company_financials, tr, ps, sc, flags, sent)
    assert nar.direction == "BUY"
    assert nar.confidence == "High"
    assert nar.executive_summary == "Solid."
    assert nar.bullish == ["x", "y"]


def test_parser_falls_back_to_raw_text(monkeypatch, strong_company_financials):
    """If structured + JSON parsing both fail, raw prose becomes the summary."""
    text = "The company has strong fundamentals and growing margins, suggesting upside."

    class OkClient:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k):
            return _streaming_response(text)

    monkeypatch.setattr(llm.ollama, "Client", OkClient)
    tr, ps, sc, flags, sent = _full_context(strong_company_financials)
    nar = llm.narrate(strong_company_financials, tr, ps, sc, flags, sent)
    assert "strong fundamentals" in nar.executive_summary


def test_on_token_callback_fires(monkeypatch, strong_company_financials):
    text = "SUMMARY: hi.\nDIRECTION: HOLD\nCONFIDENCE: Low\n"

    class OkClient:
        def __init__(self, *a, **k): pass
        def chat(self, *a, **k):
            return _streaming_response(text)

    monkeypatch.setattr(llm.ollama, "Client", OkClient)
    tr, ps, sc, flags, sent = _full_context(strong_company_financials)
    tokens: list[str] = []
    llm.narrate(strong_company_financials, tr, ps, sc, flags, sent, on_token=tokens.append)
    assert len(tokens) == len(text)
