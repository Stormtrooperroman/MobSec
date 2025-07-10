import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from app.dynamic.emulator_manager import EmulatorManager
import os

logger = logging.getLogger(__name__)

router = APIRouter()


def get_emulator_manager():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    emulators_path = os.getenv("EMULATORS_PATH", "/app/emulators")
    return EmulatorManager(redis_url, emulators_path)


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        emulator_name = request.get("name", "unknown")
        logger.error(f"Failed to start emulator {emulator_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start emulator: {str(e)}",
        )


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
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to stop emulator {emulator_name}",
            )
    except Exception as e:
        emulator_name = request.get("name", "unknown")
        logger.error(f"Failed to stop emulator {emulator_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop emulator: {str(e)}",
        )


@router.get("/status/{emulator_name}")
async def get_emulator_status(
    emulator_name: str,
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """Get status of a specific emulator"""
    try:
        status_data = await emulator_manager.get_emulator_status(emulator_name)
        if "error" in status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=status_data["error"]
            )
        return status_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get emulator status for {emulator_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emulator status: {str(e)}",
        )


@router.get("/list")
async def list_emulators(
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """List all emulators"""
    try:
        emulators = await emulator_manager.list_emulators()
        return {"emulators": emulators}
    except Exception as e:
        logger.error(f"Failed to list emulators: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list emulators: {str(e)}",
        )


@router.post("/cleanup")
async def cleanup_emulators(
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """Clean up all emulators"""
    try:
        await emulator_manager.cleanup()
        return {"success": True, "message": "All emulators cleaned up successfully"}
    except Exception as e:
        logger.error(f"Failed to cleanup emulators: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup emulators: {str(e)}",
        )


@router.get("/logs/{emulator_name}")
async def get_emulator_logs(
    emulator_name: str,
    lines: int = 100,
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """Get emulator container logs"""
    try:
        status_data = await emulator_manager.get_emulator_status(emulator_name)
        if "error" in status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=status_data["error"]
            )

        container_id = status_data.get("container_id")
        if not container_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No container found for emulator {emulator_name}",
            )

        # Get container logs
        try:
            container = emulator_manager.docker_client.containers.get(container_id)
            logs = container.logs(tail=lines, timestamps=True).decode("utf-8")

            return {
                "emulator_name": emulator_name,
                "container_id": container_id,
                "container_status": container.status,
                "logs": logs.split("\n"),
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get container logs: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get logs for emulator {emulator_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get emulator logs: {str(e)}",
        )
