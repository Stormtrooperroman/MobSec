from fastapi import APIRouter, HTTPException
from app.core.settings_db import AsyncSessionLocal
from app.models.settings import Settings
from typing import Dict, Any
from sqlalchemy import select

router = APIRouter()


async def get_db():
    async with AsyncSessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()


async def load_settings() -> Dict[str, Any]:
    async with AsyncSessionLocal() as db:
        query = select(Settings)
        result = await db.execute(query)
        settings = result.scalar_one_or_none()

        if not settings:
            # Return default settings if no settings exist
            return {
                "zip_action": None,
                "zip_action_type": None,
                "apk_action": None,
                "apk_action_type": None,
                "ipa_action": None,
                "ipa_action_type": None,
            }
        return settings.to_dict()


async def save_settings(settings_data: Dict[str, Any]) -> None:
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


@router.get("/auto-run")
async def get_auto_run_settings():
    return await load_settings()


@router.post("/auto-run")
async def update_auto_run_settings(settings: Dict[str, Any]):
    # Validate incoming settings
    required_keys = [
        "zip_action",
        "zip_action_type",
        "apk_action",
        "apk_action_type",
        "ipa_action",
        "ipa_action_type",
    ]
    for key in required_keys:
        if key not in settings:
            settings[key] = None

    # Validate action types
    valid_action_types = [None, "module", "chain"]
    for action_type_key in ["zip_action_type", "apk_action_type", "ipa_action_type"]:
        if settings[action_type_key] not in valid_action_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {action_type_key}. Must be one of: {valid_action_types}",
            )

    await save_settings(settings)
    return settings
