"""Top-level CLI orchestration."""

from __future__ import annotations

import asyncio
import re
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from . import guide, market, movers, render, report

load_dotenv()

app = typer.Typer(
    add_completion=False,
    help="Terminal quantitative equity research CLI.",
    context_settings={"help_option_names": []},
)

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,7}$")
_console = Console()


def _normalize_ticker(raw: str) -> Optional[str]:
    t = raw.strip().upper()
    return t if _TICKER_RE.match(t) else None


async def _run_report(ticker: str, with_llm: bool, deep: bool, model: Optional[str]) -> None:
    _console.print(f"[dim]Gathering data for {ticker}…[/]")
    status = _console.status("[cyan]starting…", spinner="dots")
    status.start()

    def on_stage(name: str) -> None:
        status.update(f"[cyan]{name}[/]")

    try:
        try:
            r = await report.build(
                ticker,
                with_llm=with_llm,
                deep_paragraphs=deep,
                model=model,
                on_stage=on_stage,
            )
        finally:
            status.stop()
    except Exception as e:
        _console.print(f"[red]Failed to build report for {ticker}: {e}[/]")
        return

    if r.stage_timings:
        parts = [f"{k}: {v:.1f}s" for k, v in r.stage_timings.items()]
        total = sum(r.stage_timings.values())
        _console.print(f"[dim]Timings — {' · '.join(parts)} · total: {total:.1f}s[/]")
    render.render_report(_console, r)


async def _ticker_loop(with_llm: bool, deep: bool, model: Optional[str]) -> None:
    while True:
        raw = typer.prompt("\nEnter a ticker (or 'q' to quit)", default="q", show_default=False)
        if raw.strip().lower() in {"q", "quit", "exit"}:
            _console.print("[dim]Bye.[/]")
            return
        ticker = _normalize_ticker(raw)
        if ticker is None:
            _console.print(f"[red]'{raw}' isn't a valid ticker. Try again.[/]")
            continue
        await _run_report(ticker, with_llm=with_llm, deep=deep, model=model)


async def _main(with_llm: bool, deep: bool, model: Optional[str], single: Optional[str]) -> None:
    if single:
        ticker = _normalize_ticker(single)
        if ticker is None:
            _console.print(f"[red]'{single}' isn't a valid ticker.[/]")
            raise typer.Exit(code=2)
        await _run_report(ticker, with_llm=with_llm, deep=deep, model=model)
        return

    status = market.check_nyse()
    if status.is_open:
        _console.print(f"[green]✓ NYSE open ({status.as_of})[/]")
        with _console.status("[cyan]Fetching today's top gainers…", spinner="dots"):
            top = await movers.top_gainers(limit=5)
        render.render_movers(_console, top)
    else:
        render.render_market_closed(_console, status.reason, status.as_of)

    await _ticker_loop(with_llm=with_llm, deep=deep, model=model)


def _help_callback(ctx: typer.Context, value: bool) -> None:
    """Custom --help: standard usage block on top, then the educational guide."""
    if not value or ctx.resilient_parsing:
        return
    _console.print(ctx.get_help())
    _console.print()
    guide.render_guide(_console)
    raise typer.Exit()


@app.command(context_settings={"help_option_names": []})
def main(
    ticker: Optional[str] = typer.Argument(None, help="If given, produce a single report and exit."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM prose (still produces scores + tables)."),
    deep: bool = typer.Option(False, "--deep", help="Also generate the four deep-dive paragraphs (slower)."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Ollama model to use (overrides OLLAMA_MODEL env var)."),
    help_: bool = typer.Option(
        False, "--help", "-h",
        is_eager=True, callback=_help_callback,
        help="Show usage plus a guide to what numeric stats make a stock worth a closer look.",
    ),
) -> None:
    """Run the equity research CLI."""
    asyncio.run(_main(with_llm=not no_llm, deep=deep, model=model, single=ticker))


if __name__ == "__main__":
    app()
