from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from .database import create_engine_from_url, create_session_factory


class DatabaseManager:
    def __init__(self, database_url: str) -> None:
        self.engine = create_engine_from_url(database_url)
        self.session_factory = create_session_factory(self.engine)

    async def close(self) -> None:
        await self.engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


async def get_db_session(db_manager: DatabaseManager) -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session
