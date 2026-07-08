import asyncio
import csv
import io
import math

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

import crud
from db import session_scope

KEYWORDS_PAGE_SIZE = 10
BROADCAST_DELAY = 0.05  # seconds between messages, keeps us under Telegram limits


class IsAdmin(BaseFilter):
    async def __call__(self, event) -> bool:
        async with session_scope() as session:
            return await crud.is_admin(session, event.from_user.id)


router = Router()
router.message.filter(F.chat.type == "private", IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject, bot: Bot):
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /broadcast <message text>")
        return

    async with session_scope() as session:
        user_ids = await crud.active_user_ids(session)

    status = await message.answer(f"Sending the message to {len(user_ids)} users...")
    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(user_id, text)
                sent += 1
            except TelegramAPIError:
                failed += 1
        except TelegramForbiddenError:
            # The user blocked the bot, skip them in future broadcasts
            async with session_scope() as session:
                await crud.deactivate_user(session, user_id)
            failed += 1
        except TelegramAPIError as e:
            logger.warning("Broadcast to {} failed: {}", user_id, e)
            failed += 1
        await asyncio.sleep(BROADCAST_DELAY)

    await status.edit_text(f"Broadcast finished. Sent: {sent}, failed: {failed}.")
    logger.info("Broadcast done: sent={} failed={}", sent, failed)


@router.message(Command("users"))
async def cmd_users(message: Message):
    async with session_scope() as session:
        total = await crud.count_users(session)
        week = await crud.count_new_users(session, days=7)
    await message.answer(f"Registered users: {total}\nNew in the last 7 days: {week}")


@router.message(Command("export"))
async def cmd_export(message: Message):
    async with session_scope() as session:
        users = await crud.all_users(session)
    if not users:
        await message.answer("There are no users yet.")
        return

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["user_id", "username", "first_name", "last_name", "joined_at", "last_seen", "active"]
    )
    for user in users:
        writer.writerow([
            user.id,
            user.username or "",
            user.first_name or "",
            user.last_name or "",
            user.joined_at,
            user.last_seen,
            1 if user.is_active else 0,
        ])

    # utf-8-sig, so the file opens correctly in Excel
    document = BufferedInputFile(buffer.getvalue().encode("utf-8-sig"), filename="users.csv")
    await message.answer_document(document, caption=f"{len(users)} users")


@router.message(Command("addkeyword"))
async def cmd_addkeyword(message: Message, command: CommandObject):
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: /addkeyword <keyword> <reply text>\n"
            "Example: /addkeyword price Our price list: ..."
        )
        return
    word = parts[0].lower()
    reply = parts[1].strip()
    async with session_scope() as session:
        created = await crud.set_keyword(session, word, reply)
    await message.answer(f'Keyword "{word}" {"added" if created else "updated"}.')


@router.message(Command("removekeyword"))
async def cmd_removekeyword(message: Message, command: CommandObject):
    word = (command.args or "").strip().lower()
    if not word:
        await message.answer("Usage: /removekeyword <keyword>")
        return
    async with session_scope() as session:
        removed = await crud.remove_keyword(session, word)
    if removed:
        await message.answer(f'Keyword "{word}" removed.')
    else:
        await message.answer(f'Keyword "{word}" was not found. Check /listkeywords.')


def build_keywords_page(keywords, page: int):
    pages = max(1, math.ceil(len(keywords) / KEYWORDS_PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    start = page * KEYWORDS_PAGE_SIZE

    lines = []
    for kw in keywords[start:start + KEYWORDS_PAGE_SIZE]:
        preview = " ".join(kw.reply.split())  # keep multiline replies on one line
        if len(preview) > 60:
            preview = preview[:57] + "..."
        lines.append(f"{kw.word} - {preview}")
    text = f"Keywords ({len(keywords)} total), page {page + 1} of {pages}:\n\n" + "\n".join(lines)

    keyboard = None
    if pages > 1:
        buttons = []
        if page > 0:
            buttons.append(
                InlineKeyboardButton(text="< Prev", callback_data=f"kwpage:{page - 1}")
            )
        if page < pages - 1:
            buttons.append(
                InlineKeyboardButton(text="Next >", callback_data=f"kwpage:{page + 1}")
            )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons])
    return text, keyboard


@router.message(Command("listkeywords"))
async def cmd_listkeywords(message: Message):
    async with session_scope() as session:
        keywords = await crud.get_keywords(session)
    if not keywords:
        await message.answer("No keywords yet. Add one with /addkeyword.")
        return
    text, keyboard = build_keywords_page(keywords, 0)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("kwpage:"))
async def cb_keywords_page(callback: CallbackQuery):
    page = int(callback.data.split(":", 1)[1])
    async with session_scope() as session:
        keywords = await crud.get_keywords(session)
    text, keyboard = build_keywords_page(keywords, page)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass  # same page requested twice, nothing to change
    await callback.answer()
