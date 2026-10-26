import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://postgres:password@db:5432/mobsec_db"
        )
        self.engine = create_async_engine(self.database_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Database connection manager initialized")

    @property
    def session_factory(self):
        return self.async_session


db_manager = DatabaseManager()


async def init_db():
    from .frida_script_model import Base

    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
