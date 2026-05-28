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
from typing import Optional

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

from . import report as report_mod
from .telegram_format import (
    escape_mdv2,
    format_error,
    format_help,
    format_report,
)


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

    raw = (message.text or "").strip().upper()
    if not _TICKER_RE.match(raw):
        await message.reply_text("Send a ticker like AAPL.")
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
