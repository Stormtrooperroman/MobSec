from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.core.settings_service import settings_service

router = APIRouter()


async def load_settings() -> Dict[str, Any]:
    return await settings_service.get_settings()


async def save_settings(settings_data: Dict[str, Any]) -> None:
    await settings_service.save_settings(settings_data)


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
