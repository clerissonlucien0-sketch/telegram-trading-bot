import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScope, BotCommandScopeChat
from loguru import logger

from config import BOT_TOKEN
from db import close_db
from handlers import admin, user
from middlewares import TrackUsersMiddleware
from utils import setup_logging


async def set_commands(bot: Bot):
    """Set commands for regular users and admins."""
    # Commands for all users
    user_commands = [
        BotCommand(command="start", description="Show the welcome message"),
        BotCommand(command="help", description="Show all available commands"),
    ]
    await bot.set_my_commands(user_commands)
    
    logger.info("User commands registered")


async def main():
    setup_logging()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.outer_middleware(TrackUsersMiddleware())
    dp.include_routers(admin.router, user.router)

    # Set up commands
    await set_commands(bot)

    logger.info("Bot started successfully")
    try:
        await dp.start_polling(bot)
    finally:
        await close_db()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
