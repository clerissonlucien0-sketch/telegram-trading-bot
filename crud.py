from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models import Admin, Keyword, User


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def upsert_user(session: AsyncSession, tg_user) -> None:
    """Insert or update a user based on Telegram user data."""
    try:
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
    except Exception as e:
        logger.error("Failed to upsert user {}: {}", tg_user.id, e)
        raise


async def count_users(session: AsyncSession) -> int:
    """Count total registered users."""
    try:
        return await session.scalar(select(func.count()).select_from(User)) or 0
    except Exception as e:
        logger.error("Failed to count users: {}", e)
        return 0


async def count_new_users(session: AsyncSession, days: int) -> int:
    """Count users who joined in the last N days."""
    try:
        since = _utcnow() - timedelta(days=days)
        return await session.scalar(
            select(func.count()).select_from(User).where(User.joined_at >= since)
        ) or 0
    except Exception as e:
        logger.error("Failed to count new users: {}", e)
        return 0


async def active_user_ids(session: AsyncSession) -> list[int]:
    """Get list of all active user IDs."""
    try:
        result = await session.scalars(select(User.id).where(User.is_active))
        return list(result)
    except Exception as e:
        logger.error("Failed to get active user IDs: {}", e)
        return []


async def all_users(session: AsyncSession) -> list[User]:
    """Get all users ordered by join date."""
    try:
        result = await session.scalars(select(User).order_by(User.joined_at))
        return list(result)
    except Exception as e:
        logger.error("Failed to get all users: {}", e)
        return []


async def deactivate_user(session: AsyncSession, user_id: int) -> None:
    """Mark a user as inactive (e.g., they blocked the bot)."""
    try:
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=False)
        )
        logger.info("User {} deactivated", user_id)
    except Exception as e:
        logger.error("Failed to deactivate user {}: {}", user_id, e)
        raise


async def add_admin(session: AsyncSession, user_id: int, username: Optional[str]) -> bool:
    """Grant admin access to a user. Returns True if new, False if already admin."""
    try:
        if await session.get(Admin, user_id) is not None:
            return False
        session.add(Admin(user_id=user_id, username=username))
        return True
    except Exception as e:
        logger.error("Failed to add admin {}: {}", user_id, e)
        raise


async def is_admin(session: AsyncSession, user_id: int) -> bool:
    """Check if a user has admin privileges."""
    try:
        return await session.get(Admin, user_id) is not None
    except Exception as e:
        logger.error("Failed to check admin status for {}: {}", user_id, e)
        return False


async def set_keyword(session: AsyncSession, word: str, reply: str) -> bool:
    """Add or update a keyword. Returns True if created, False if updated."""
    try:
        existing = await session.scalar(select(Keyword).where(Keyword.word == word))
        if existing is not None:
            existing.reply = reply
            return False
        session.add(Keyword(word=word, reply=reply))
        return True
    except Exception as e:
        logger.error("Failed to set keyword '{}': {}", word, e)
        raise


async def remove_keyword(session: AsyncSession, word: str) -> bool:
    """Remove a keyword. Returns True if found and deleted, False otherwise."""
    try:
        result = await session.execute(delete(Keyword).where(Keyword.word == word))
        return result.rowcount > 0
    except Exception as e:
        logger.error("Failed to remove keyword '{}': {}", word, e)
        raise


async def get_keywords(session: AsyncSession) -> list[Keyword]:
    """Get all keywords sorted alphabetically."""
    try:
        result = await session.scalars(select(Keyword).order_by(Keyword.word))
        return list(result)
    except Exception as e:
        logger.error("Failed to get keywords: {}", e)
        return []
