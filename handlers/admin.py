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
    """Send a message to all active users with proper error handling and retry logic."""
    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage: /broadcast <message text>")
        return

    async with session_scope() as session:
        user_ids = await crud.active_user_ids(session)

    if not user_ids:
        await message.answer("No active users to broadcast to.")
        return

    status = await message.answer(f"📡 Sending message to {len(user_ids)} users...")
    sent = 0
    failed = 0
    blocked = 0
    
    logger.info("Starting broadcast to {} users", len(user_ids))
    
    for idx, user_id in enumerate(user_ids):
        try:
            await bot.send_message(user_id, text)
            sent += 1
        except TelegramRetryAfter as e:
            # Telegram rate limit - wait and retry
            logger.info("Rate limit hit, waiting {} seconds", e.retry_after)
            await asyncio.sleep(e.retry_after)
            try:
                await bot.send_message(user_id, text)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
                async with session_scope() as session:
                    await crud.deactivate_user(session, user_id)
            except TelegramAPIError as e:
                logger.warning("Retry failed for user {}: {}", user_id, e)
                failed += 1
        except TelegramForbiddenError:
            # User blocked the bot - deactivate them
            blocked += 1
            async with session_scope() as session:
                await crud.deactivate_user(session, user_id)
        except TelegramAPIError as e:
            logger.warning("Broadcast to {} failed: {}", user_id, e)
            failed += 1
        
        # Update progress every 50 messages
        if (idx + 1) % 50 == 0:
            progress = f"📡 Progress: {idx + 1}/{len(user_ids)} (✓ {sent}, ✗ {failed}, 🚫 {blocked})"
            try:
                await status.edit_text(progress)
            except TelegramBadRequest:
                pass
        
        await asyncio.sleep(BROADCAST_DELAY)

    result_text = f"✅ Broadcast finished!\nSent: {sent}/{len(user_ids)}\nFailed: {failed}\nBlocked: {blocked}"
    await status.edit_text(result_text)
    logger.info("Broadcast complete: sent={}, failed={}, blocked={}", sent, failed, blocked)


@router.message(Command("users"))
async def cmd_users(message: Message):
    """Show user statistics."""
    async with session_scope() as session:
        total = await crud.count_users(session)
        week = await crud.count_new_users(session, days=7)
    
    stats = f"👥 **User Statistics**\n\n"
    stats += f"Total registered users: {total}\n"
    stats += f"New in the last 7 days: {week}"
    await message.answer(stats)


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Export user list as CSV."""
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
    await message.answer_document(document, caption=f"📊 {len(users)} users exported")
    logger.info("Exported {} users", len(users))


@router.message(Command("addkeyword"))
async def cmd_addkeyword(message: Message, command: CommandObject):
    """Add or update a keyword trigger."""
    parts = (command.args or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Usage: /addkeyword <keyword> <reply text>\n"
            "Example: /addkeyword price Our price list: ..."
        )
        return
    word = parts[0].lower()
    reply = parts[1].strip()
    
    if len(word) < 1 or len(word) > 64:
        await message.answer("Keyword must be between 1 and 64 characters.")
        return
    
    if len(reply) < 1 or len(reply) > 4096:
        await message.answer("Reply must be between 1 and 4096 characters.")
        return
    
    async with session_scope() as session:
        created = await crud.set_keyword(session, word, reply)
    
    action = "added" if created else "updated"
    await message.answer(f'✅ Keyword "{word}" {action}.')
    logger.info("Keyword '{}' {}", word, action)


@router.message(Command("removekeyword"))
async def cmd_removekeyword(message: Message, command: CommandObject):
    """Remove a keyword trigger."""
    word = (command.args or "").strip().lower()
    if not word:
        await message.answer("Usage: /removekeyword <keyword>")
        return
    
    async with session_scope() as session:
        removed = await crud.remove_keyword(session, word)
    
    if removed:
        await message.answer(f'✅ Keyword "{word}" removed.')
        logger.info("Keyword '{}' removed", word)
    else:
        await message.answer(f'❌ Keyword "{word}" was not found. Check /listkeywords.')


def build_keywords_page(keywords, page: int):
    """Build a paginated view of keywords."""
    pages = max(1, math.ceil(len(keywords) / KEYWORDS_PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    start = page * KEYWORDS_PAGE_SIZE

    lines = []
    for kw in keywords[start:start + KEYWORDS_PAGE_SIZE]:
        preview = " ".join(kw.reply.split())  # keep multiline replies on one line
        if len(preview) > 60:
            preview = preview[:57] + "..."
        lines.append(f"🔑 {kw.word} - {preview}")
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
    """Show all configured keywords."""
    async with session_scope() as session:
        keywords = await crud.get_keywords(session)
    
    if not keywords:
        await message.answer("No keywords yet. Add one with /addkeyword.")
        return
    
    text, keyboard = build_keywords_page(keywords, 0)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("kwpage:"))
async def cb_keywords_page(callback: CallbackQuery):
    """Handle pagination for keyword list."""
    try:
        page = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Invalid page number")
        return
    
    async with session_scope() as session:
        keywords = await crud.get_keywords(session)
    
    text, keyboard = build_keywords_page(keywords, page)
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest:
        pass  # same page requested twice, nothing to change
    await callback.answer()
