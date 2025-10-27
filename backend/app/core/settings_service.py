"""Service for managing settings"""

import logging
from typing import Any, Dict

from sqlalchemy import select

from app.core.settings_db import AsyncSessionLocal
from app.models.settings import Settings

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings"""

    @staticmethod
    async def get_settings() -> Dict[str, Any]:
        """Get settings from database"""
        async with AsyncSessionLocal() as db:
            query = select(Settings)
            result = await db.execute(query)
            settings = result.scalar_one_or_none()

            if not settings:
                return {
                    "zip_action": None,
                    "zip_action_type": None,
                    "apk_action": None,
                    "apk_action_type": None,
                    "ipa_action": None,
                    "ipa_action_type": None,
                }
            return settings.to_dict()

    @staticmethod
    async def save_settings(settings_data: Dict[str, Any]) -> None:
        """Save settings to database"""
        async with AsyncSessionLocal() as db:
            query = select(Settings)
            result = await db.execute(query)
            settings = result.scalar_one_or_none()

            if settings:
                for key, value in settings_data.items():
                    setattr(settings, key, value)
            else:
                settings = Settings(id="global", **settings_data)
                db.add(settings)
            await db.commit()


# Global instance
settings_service = SettingsService()

