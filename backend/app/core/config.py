import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql+asyncpg://user:password@db:5432/mobsec"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", "/app/reports")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    API_V1_STR: str = "/api/v1"
    # ALLOWED_ORIGINS: List[str] = ["http://localhost:4200"]

    EXTERNAL_MODULES_ENABLED: bool = (
        os.getenv("EXTERNAL_MODULES_ENABLED", "True").lower() == "true"
    )
    MODULES_HEALTH_CHECK_INTERVAL: int = int(
        os.getenv("MODULES_HEALTH_CHECK_INTERVAL", "30")
    )  # health check interval in seconds


settings = Settings()
