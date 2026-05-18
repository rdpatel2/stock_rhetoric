"""Educational `--help` companion guide."""

from rich.console import Console

from stock_rhetoric import guide


def test_render_guide_emits_categories():
    console = Console(record=True, width=120)
    guide.render_guide(console)
    out = console.export_text()
    # Every section heading appears in the rendered output.
    for heading in (
        "Growth",
        "Profitability & margins",
        "Valuation",
        "Balance sheet",
        "Cash flow quality",
        "Shareholder returns",
        "Red flags",
        "How to read this report",
    ):
        assert heading in out, f"missing section: {heading}"
    # Disclaimer is appended at the bottom.
    assert "Not financial advice" in out


def test_render_guide_documents_trend_glyphs():
    """The guide must explain the new five-state trend glyph scheme."""
    console = Console(record=True, width=120)
    guide.render_guide(console)
    out = console.export_text()
    for glyph in ("─", ">", ">>", "<", "<<"):
        assert glyph in out, f"trend glyph not documented: {glyph}"
