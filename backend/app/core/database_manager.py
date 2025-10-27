"""Database connection manager"""

import logging
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions"""

    def __init__(self, database_url: str = None):
        """Initialize database manager"""
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
        """Get session factory"""
        return self.async_session


# Global instance
db_manager = DatabaseManager()

