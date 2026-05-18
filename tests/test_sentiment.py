"""VADER + finance-lexicon sentiment scoring."""

from stock_rhetoric import sentiment
from stock_rhetoric.aggregator import SentimentBundle
from stock_rhetoric.sources.base import SourceItem


def _item(title: str, snippet: str = "", tier: str = "reliable") -> SourceItem:
    return SourceItem(tier=tier, source="Test", title=title, snippet=snippet, url="https://x")


def test_positive_headline_scores_positive():
    _, label = sentiment.score("NVDA beats earnings, raises guidance and forecasts record quarter")
    assert label == "positive"


def test_negative_headline_scores_negative():
    _, label = sentiment.score("Tesla deliveries miss estimates, stock plunges on disappointing outlook")
    assert label == "negative"


def test_neutral_headline_scores_neutral():
    _, label = sentiment.score("Apple to host product event next week in Cupertino")
    assert label == "neutral"


def test_finance_lexicon_overrides_default():
    """'downgrade' should resolve negative even though VADER's default treats it weakly."""
    score, label = sentiment.score("Analyst downgrade for company")
    assert label == "negative"
    assert score < -0.15


def test_score_items_mutates_in_place():
    items = [
        _item("Stock surges on record profits"),
        _item("Company faces lawsuit and probe"),
        _item("Quarterly report scheduled for Tuesday"),
    ]
    sentiment.score_items(items)
    assert items[0].sentiment_label == "positive"
    assert items[1].sentiment_label == "negative"
    assert items[2].sentiment_label == "neutral"
    for it in items:
        assert it.sentiment_score is not None


def test_bundle_tone_summary():
    bundle = SentimentBundle(items=[
        _item("Stock rallies on upgrade"),
        _item("Earnings beat boosts shares"),
        _item("Lawsuit filed against company"),
        _item("Quarterly filing released"),
    ])
    sentiment.score_items(bundle.items)
    summary = bundle.tone_summary()
    assert summary["positive"] == 2
    assert summary["negative"] == 1
    assert summary["neutral"] == 1
    assert -1.0 <= summary["net"] <= 1.0


def test_score_handles_empty_text():
    score, label = sentiment.score("")
    assert score == 0.0
    assert label == "neutral"
