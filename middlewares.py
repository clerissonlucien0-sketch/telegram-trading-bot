from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

import crud
from db import session_scope


class TrackUsersMiddleware(BaseMiddleware):
    """Saves everyone who talks to the bot, so /broadcast can reach them later."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        chat = data.get("event_chat")
        if user is not None and not user.is_bot and chat is not None and chat.type == "private":
            async with session_scope() as session:
                await crud.upsert_user(session, user)
        return await handler(event, data)
