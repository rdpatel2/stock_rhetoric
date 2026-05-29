"""Telegram bot front-end for stock-rhetoric.

Long-polls the Bot API (no public URL or webhook needed). On each allowed-user
message, runs `report.build()` and posts the formatted result back.

Started by the `stock-rhetoric-bot` console entry point; designed to run under
systemd (see `deploy/stock-rhetoric-bot.service`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import market, report as report_mod, watchlist
from .telegram_format import (
    escape_mdv2,
    format_digest,
    format_error,
    format_help,
    format_report,
    format_watchlist_ack,
    format_watchlist_list,
)


_NY = ZoneInfo("America/New_York")


log = logging.getLogger("stock_rhetoric.bot")

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_USER_LOCKS: dict[int, asyncio.Lock] = {}


def _parse_ids(raw: str) -> set[int]:
    out: set[int] = set()
    for piece in (raw or "").split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.add(int(piece))
        except ValueError:
            log.warning("Ignoring non-integer Telegram user id: %r", piece)
    return out


def _user_lock(user_id: int) -> asyncio.Lock:
    lock = _USER_LOCKS.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _USER_LOCKS[user_id] = lock
    return lock


def _allowed(update: Update, allowlist: set[int]) -> bool:
    u = update.effective_user
    return bool(u and u.id in allowlist)


async def _typing_loop(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Re-send the typing action every 4 s until cancelled."""
    try:
        while True:
            await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
    except Exception:  # never let the indicator crash the request
        log.exception("Typing indicator failed")


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    allowlist: set[int] = ctx.bot_data["allowlist"]
    if not _allowed(update, allowlist):
        if not ctx.bot_data["silent_reject"]:
            await update.message.reply_text("Not authorized.")
        return
    await update.message.reply_text(format_help(), parse_mode=ParseMode.MARKDOWN_V2)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    allowlist: set[int] = ctx.bot_data["allowlist"]
    silent_reject: bool = ctx.bot_data["silent_reject"]
    llm_model: Optional[str] = ctx.bot_data["llm_model"]
    llm_timeout: float = ctx.bot_data["llm_timeout"]

    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return

    if user.id not in allowlist:
        log.info("Rejected user_id=%s username=%s", user.id, user.username)
        if not silent_reject:
            await message.reply_text("Not authorized.")
        return

    raw = (message.text or "").strip()
    parts = raw.upper().split(maxsplit=1)
    verb = parts[0] if parts else ""

    if verb == "ADD" and len(parts) == 2:
        await _handle_add(message, user.id, parts[1])
        return
    if verb in {"REMOVE", "RM"} and len(parts) == 2:
        await _handle_remove(message, user.id, parts[1])
        return
    if verb in {"LIST", "WATCHLIST"}:
        await _handle_list(message, user.id)
        return

    raw = raw.upper()
    if not _TICKER_RE.match(raw):
        await message.reply_text(
            "Send a ticker like AAPL, or `add AAPL` / `remove AAPL` / `list`."
        )
        return

    lock = _user_lock(user.id)
    if lock.locked():
        await message.reply_text("Still working on your previous request — give it a moment.")
        return

    async with lock:
        chat_id = message.chat_id
        placeholder = await message.reply_text(f"Building {raw}… (10–60s)")
        typing_task = asyncio.create_task(_typing_loop(ctx, chat_id))

        log.info("build request user_id=%s ticker=%s", user.id, raw)
        try:
            result = await report_mod.build(
                raw,
                with_llm=True,
                deep_paragraphs=False,
                model=llm_model,
                llm_timeout=llm_timeout,
            )
            text = format_report(result)
            try:
                await ctx.bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=placeholder.message_id,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except BadRequest as e:
                log.warning("MarkdownV2 parse failed, retrying plain: %s", e)
                await ctx.bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=placeholder.message_id,
                )
            log.info(
                "build done user_id=%s ticker=%s timings=%s",
                user.id, raw, result.stage_timings,
            )
        except Exception as e:
            log.exception("build failed user_id=%s ticker=%s", user.id, raw)
            try:
                await ctx.bot.edit_message_text(
                    format_error(raw, e),
                    chat_id=chat_id,
                    message_id=placeholder.message_id,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except BadRequest:
                await ctx.bot.edit_message_text(
                    f"{raw}: {type(e).__name__}: {e}",
                    chat_id=chat_id,
                    message_id=placeholder.message_id,
                )
        finally:
            typing_task.cancel()


async def _handle_add(message, user_id: int, raw_ticker: str) -> None:
    status, norm = await asyncio.to_thread(watchlist.add, str(user_id), raw_ticker)
    count = len(watchlist.get(str(user_id)))
    text = format_watchlist_ack(status, norm, count=count)
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    log.info("watchlist add user_id=%s ticker=%s status=%s", user_id, norm, status)


async def _handle_remove(message, user_id: int, raw_ticker: str) -> None:
    status, norm = await asyncio.to_thread(watchlist.remove, str(user_id), raw_ticker)
    count = len(watchlist.get(str(user_id)))
    text = format_watchlist_ack(status, norm, count=count)
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN_V2)
    log.info("watchlist remove user_id=%s ticker=%s status=%s", user_id, norm, status)


async def _handle_list(message, user_id: int) -> None:
    tickers = await asyncio.to_thread(watchlist.get, str(user_id))
    quotes = await watchlist.build_digest(tickers) if tickers else []
    await message.reply_text(
        format_watchlist_list(quotes), parse_mode=ParseMode.MARKDOWN_V2
    )


async def _run_digest(ctx: ContextTypes.DEFAULT_TYPE, mode: str) -> None:
    """Build and send the open/close digest to every user who has a watchlist."""
    if not await asyncio.to_thread(lambda: market.check_nyse().is_open):
        log.info("digest %s skipped: market closed", mode)
        return

    allowlist: set[int] = ctx.bot_data.get("allowlist", set())
    data = await asyncio.to_thread(watchlist.load)
    for user_key, tickers in data.items():
        if not tickers:
            continue
        try:
            user_id = int(user_key)
        except ValueError:
            continue  # 'cli' or other non-numeric keys
        if user_id not in allowlist:
            continue
        try:
            quotes = await watchlist.build_digest(tickers)
            text = format_digest(mode, quotes)
            try:
                await ctx.bot.send_message(
                    chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN_V2
                )
            except BadRequest as e:
                log.warning("digest MarkdownV2 send failed, retrying plain: %s", e)
                await ctx.bot.send_message(chat_id=user_id, text=text)
            log.info("digest %s sent user_id=%s tickers=%d", mode, user_id, len(tickers))
        except Exception:
            log.exception("digest %s failed for user_id=%s", mode, user_id)


async def _open_digest_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_digest(ctx, "open")


async def _close_digest_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _run_digest(ctx, "close")


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled bot error", exc_info=ctx.error)


def _build_app() -> Application:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")

    allowlist = _parse_ids(os.environ.get("TELEGRAM_ALLOWED_USER_IDS", ""))
    if not allowlist:
        log.warning("TELEGRAM_ALLOWED_USER_IDS is empty — bot will reject every message.")

    app = ApplicationBuilder().token(token).build()
    app.bot_data["allowlist"] = allowlist
    app.bot_data["silent_reject"] = os.environ.get("TELEGRAM_SILENT_REJECT", "1") == "1"
    app.bot_data["llm_model"] = os.environ.get("OLLAMA_MODEL") or None
    app.bot_data["llm_timeout"] = float(os.environ.get("OLLAMA_TIMEOUT_S", "120"))

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    if app.job_queue is None:
        log.warning(
            "JobQueue unavailable — install python-telegram-bot[job-queue]; "
            "watchlist digests will not run."
        )
    else:
        app.job_queue.run_daily(
            _open_digest_job, time=dtime(9, 30, tzinfo=_NY), name="open_digest"
        )
        app.job_queue.run_daily(
            _close_digest_job, time=dtime(16, 30, tzinfo=_NY), name="close_digest"
        )
        log.info("scheduled watchlist digests: open 09:30 ET, close 16:30 ET")
    return app


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Silence noisy HTTP libraries.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.INFO)

    app = _build_app()
    log.info("starting long-polling loop")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
