"""CLI behavior — focuses on the custom --help guide screen."""

from typer.testing import CliRunner

from stock_rhetoric.cli import app


def test_help_flag_renders_guide_and_exits():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    # Usage block from typer (top pane).
    assert "Usage:" in result.output
    # Guide content (bottom pane).
    assert "What to look for in a lucrative stock" in result.output
    assert "Growth" in result.output
    assert "Red flags" in result.output


def test_short_help_flag_works():
    runner = CliRunner()
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert "What to look for in a lucrative stock" in result.output
