import os
from typing import List

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/mobsec")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", "/app/reports")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    API_V1_STR: str = "/api/v1"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:4200"]

settings = Settings()
