from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import Admin, Keyword, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def upsert_user(session: AsyncSession, tg_user) -> None:
    stmt = insert(User).values(
        id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.id],
        set_={
            "username": tg_user.username,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
            "last_seen": func.now(),
            "is_active": True,
        },
    )
    await session.execute(stmt)


async def count_users(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(User))


async def count_new_users(session: AsyncSession, days: int) -> int:
    since = _utcnow() - timedelta(days=days)
    return await session.scalar(
        select(func.count()).select_from(User).where(User.joined_at >= since)
    )


async def active_user_ids(session: AsyncSession) -> list[int]:
    result = await session.scalars(select(User.id).where(User.is_active))
    return list(result)


async def all_users(session: AsyncSession) -> list[User]:
    result = await session.scalars(select(User).order_by(User.joined_at))
    return list(result)


async def deactivate_user(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(is_active=False)
    )


async def add_admin(session: AsyncSession, user_id: int, username: Optional[str]) -> bool:
    if await session.get(Admin, user_id) is not None:
        return False
    session.add(Admin(user_id=user_id, username=username))
    return True


async def is_admin(session: AsyncSession, user_id: int) -> bool:
    return await session.get(Admin, user_id) is not None


async def set_keyword(session: AsyncSession, word: str, reply: str) -> bool:
    """Returns True if the keyword was created, False if it was updated."""
    existing = await session.scalar(select(Keyword).where(Keyword.word == word))
    if existing is not None:
        existing.reply = reply
        return False
    session.add(Keyword(word=word, reply=reply))
    return True


async def remove_keyword(session: AsyncSession, word: str) -> bool:
    result = await session.execute(delete(Keyword).where(Keyword.word == word))
    return result.rowcount > 0


async def get_keywords(session: AsyncSession) -> list[Keyword]:
    result = await session.scalars(select(Keyword).order_by(Keyword.word))
    return list(result)
