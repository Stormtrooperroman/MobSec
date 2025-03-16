from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.settings import Base
import os

# Get database URL from environment variable
database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:password@db:5432/mobsec_db')

# Create async database engine
engine = create_async_engine(database_url)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) 