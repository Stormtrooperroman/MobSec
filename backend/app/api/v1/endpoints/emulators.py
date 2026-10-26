import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.dynamic.device_management.emulator_manager import EmulatorManager

logger = logging.getLogger(__name__)

router = APIRouter()


def get_emulator_manager():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    emulators_path = os.getenv("EMULATORS_PATH", "/app/emulators")
    return EmulatorManager.get_instance(redis_url, emulators_path)


@router.post("/start")
async def start_emulator(
    request: Dict[str, Any],
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """Start an emulator"""
    try:
        emulator_name = request.get("name")
        if not emulator_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Emulator name is required",
            )

        result = await emulator_manager.start_emulator(emulator_name)
        return {
            "success": True,
            "message": f"Emulator {emulator_name} started successfully",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except Exception as e:
        emulator_name = request.get("name", "unknown")
        logger.error("Failed to start emulator %s: %s", emulator_name, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start emulator: {str(e)}",
        ) from e


@router.post("/stop")
async def stop_emulator(
    request: Dict[str, Any],
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """Stop an emulator"""
    try:
        emulator_name = request.get("name")
        if not emulator_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Emulator name is required",
            )

        success = await emulator_manager.stop_emulator(emulator_name)
        if success:
            return {
                "success": True,
                "message": f"Emulator {emulator_name} stopped successfully",
            }

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop emulator {emulator_name}",
        )
    except Exception as e:
        emulator_name = request.get("name", "unknown")
        logger.error("Failed to stop emulator %s: %s", emulator_name, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop emulator: {str(e)}",
        ) from e


@router.get("/list")
async def list_emulators(
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """List all emulators"""
    try:
        emulators = await emulator_manager.list_emulators()
        return {"emulators": emulators}
    except Exception as e:
        logger.error("Failed to list emulators: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list emulators: {str(e)}",
        ) from e
