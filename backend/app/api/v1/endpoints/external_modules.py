import io
import logging
import os
import tarfile
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.app_manager import storage
from app.models.external_module import ModuleStatus
from app.modules.external_module_registry import module_registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/register")
async def register_external_module(module_data: Dict[str, Any] = Body(...)):
    """
    Register an external module.
    The module sends its configuration and URL where it can be accessed.
    """
    try:
        logger.info("%s", module_data)
        registered_module = await module_registry.register_module(module_data)
        return registered_module
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error registering module: {str(e)}"
        ) from e


@router.get("/")
async def list_external_modules(active_only: bool = False) -> List[Dict[str, Any]]:
    """Get a list of all registered external modules"""
    return await module_registry.list_modules(active_only)


@router.get("/{module_id}")
async def get_external_module(module_id: str) -> Dict[str, Any]:
    """Get information about a specific external module"""
    module = await module_registry.get_module(module_id)
    if not module:
        raise HTTPException(
            status_code=404, detail=f"Module with ID {module_id} not found"
        )
    return module


@router.delete("/{module_id}")
async def deregister_external_module(module_id: str):
    """Remove an external module registration"""
    success = await module_registry.deregister_module(module_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Module with ID {module_id} not found"
        )
    return {"message": f"Module {module_id} successfully removed from registry"}


@router.post("/{module_id}/heartbeat")
async def module_heartbeat(module_id: str):
    """Update external module activity status (heartbeat)"""
    success = await module_registry.update_module_heartbeat(module_id)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Module with ID {module_id} not found"
        )
    return {"status": "ok"}


@router.get("/{module_id}/files")
async def get_module_files(
    module_id: str,
    file_ids: List[str] = Query(...),
    _background_tasks: BackgroundTasks = None,
):
    """Get files for external module processing"""
    # Validate module
    module = await module_registry.get_module(module_id)
    if not module:
        raise HTTPException(
            status_code=404, detail=f"Module with ID {module_id} not found"
        )

    if module["status"] != ModuleStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Module {module_id} is not active")

    # Get file information
    files = await _get_files_info(file_ids)

    # Create tar archive
    tar_data = await _create_tar_archive(files)

    await module_registry.update_module_heartbeat(module_id)

    return StreamingResponse(
        io.BytesIO(tar_data),
        media_type="application/x-tar",
        headers={"Content-Disposition": "attachment; filename=app_files.tar.gz"},
    )


async def _get_files_info(file_ids: List[str]) -> List[Dict[str, Any]]:
    """Get file information for given file IDs"""
    files = []
    for file_id in file_ids:
        file_info = await storage.get_scan_status(file_id)
        if not file_info:
            logger.warning("File not found: %s", file_id)
            continue
        files.append(file_info)

    if not files:
        raise HTTPException(status_code=404, detail="No valid files found")
    return files


async def _create_tar_archive(files: List[Dict[str, Any]]) -> bytes:
    """Create tar.gz archive from files"""
    tar_buffer = io.BytesIO()

    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        for file_info in files:
            folder_path = os.path.join("/shared_data", file_info["folder_path"])

            if not os.path.exists(folder_path):
                logger.warning("Folder not found: %s", folder_path)
                continue

            _add_folder_to_tar(tar, folder_path, len(files))

    tar_buffer.seek(0)
    return tar_buffer.getvalue()


def _add_folder_to_tar(tar: tarfile.TarFile, folder_path: str, total_files: int):
    """Add folder contents to tar archive"""
    for root, _dirs, files_in_dir in os.walk(folder_path):
        for file_name in files_in_dir:
            full_path = os.path.join(root, file_name)
            rel_path = os.path.relpath(full_path, "/shared_data")

            # Determine archive path based on number of files
            if total_files == 1:
                archive_path = _get_single_file_archive_path(rel_path)
            else:
                archive_path = rel_path

            try:
                tar.add(full_path, arcname=archive_path)
            except Exception as e:
                logger.warning("Couldn't add file %s to tar: %s", full_path, e)


def _get_single_file_archive_path(rel_path: str) -> str:
    """Get archive path for single file scenario"""
    parts = rel_path.split("/", 1)
    if len(parts) > 1:
        return parts[1]
    return os.path.basename(rel_path)
