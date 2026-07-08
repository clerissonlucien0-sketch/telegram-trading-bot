import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from loguru import logger

from config import BOT_TOKEN
from db import close_db
from handlers import admin, user
from middlewares import TrackUsersMiddleware
from utils import setup_logging


async def main():
    setup_logging()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.message.outer_middleware(TrackUsersMiddleware())
    dp.include_routers(admin.router, user.router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Show the welcome message"),
        BotCommand(command="help", description="Show all available commands"),
    ])

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        await close_db()
        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
