import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message
from loguru import logger

import crud
from config import ADMIN_SECRET
from db import session_scope

router = Router()
router.message.filter(F.chat.type == "private")

WELCOME = (
    "Welcome! 🙋\n"
    "This bot helps you get quick information and automatic replies.\n"
    "Use /help to see all available commands."
)

USER_HELP = (
    "Available commands:\n"
    "/start - Show the welcome message\n"
    "/help - Show this message\n\n"
    "Send me any message and I will reply automatically "
    "if it contains a known keyword."
)

ADMIN_HELP = (
    "\n\n🔐 **Admin commands:**\n"
    "/broadcast <text> - Send a message to all users\n"
    "/users - Show user statistics\n"
    "/export - Download the user list as a CSV file\n"
    "/addkeyword <keyword> <reply text> - Add or update an automatic reply\n"
    "/removekeyword <keyword> - Remove a keyword\n"
    "/listkeywords - Show all keywords"
)

ADMIN_COMMANDS = ("broadcast", "users", "export", "addkeyword", "removekeyword", "listkeywords")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    """Handle /start command - grant admin access via deep link."""
    # /start can carry a payload from a deep link, we use it to grant admin access
    if ADMIN_SECRET and command.args == ADMIN_SECRET:
        try:
            async with session_scope() as session:
                added = await crud.add_admin(
                    session, message.from_user.id, message.from_user.username
                )
            if added:
                logger.info(
                    "Admin access granted to {} (@{})",
                    message.from_user.id,
                    message.from_user.username,
                )
                await message.answer(
                    "✅ You have admin access now. Use /help to see the admin commands."
                )
            else:
                await message.answer("ℹ️ You already have admin access.")
        except Exception as e:
            logger.error("Failed to grant admin access: {}", e)
            await message.answer("❌ An error occurred while granting admin access.")
        return
    
    await message.answer(WELCOME)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Show help message with user/admin commands."""
    try:
        async with session_scope() as session:
            admin = await crud.is_admin(session, message.from_user.id)
        await message.answer(USER_HELP + (ADMIN_HELP if admin else ""))
    except Exception as e:
        logger.error("Failed to get help message: {}", e)
        await message.answer(USER_HELP)


@router.message(Command(*ADMIN_COMMANDS))
async def cmd_admin_only(message: Message):
    """Block regular users from running admin commands."""
    await message.answer("❌ Sorry, this command is available to admins only.")


@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message):
    """Handle unknown commands."""
    await message.answer("❓ Unknown command. Use /help to see available commands.")


@router.message(F.text)
async def keyword_reply(message: Message):
    """Match and reply to messages containing keywords."""
    if not message.text:
        return
    
    try:
        async with session_scope() as session:
            keywords = await crud.get_keywords(session)
        
        text = message.text.lower()
        for kw in keywords:
            # Whole word match, so "vip" does not trigger on "viper"
            if re.search(r"\b" + re.escape(kw.word) + r"\b", text):
                try:
                    await message.answer(kw.reply)
                    logger.debug(
                        "Keyword '{}' matched for user {}",
                        kw.word,
                        message.from_user.id
                    )
                except Exception as e:
                    logger.error(
                        "Failed to send keyword reply to {}: {}",
                        message.from_user.id,
                        e
                    )
                return
    except Exception as e:
        logger.error("Error processing keyword match: {}", e)
