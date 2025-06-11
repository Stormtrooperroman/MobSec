from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Body, status
from fastapi.responses import StreamingResponse, JSONResponse
import io
from typing import List, Optional, Dict, Any
import logging
import httpx
import os
import json
from datetime import datetime
import zipfile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import tarfile

from app.models.external_module import ModuleStatus, ExternalModule
from app.modules.external_module_registry import module_registry
from app.core.app_manager import storage
from app.models.app import ScanStatus, FileModel
from app.core.settings_db import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/register")
async def register_external_module(module_data: Dict[str, Any] = Body(...)):
    """
    Register an external module.
    The module sends its configuration and URL where it can be accessed.
    """
    try:
        logger.info(f"{module_data}")
        registered_module = await module_registry.register_module(module_data)
        return registered_module
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering module: {str(e)}")

@router.get("/")
async def list_external_modules(active_only: bool = False) -> List[Dict[str, Any]]:
    """Get a list of all registered external modules"""
    return await module_registry.list_modules(active_only)

@router.get("/{module_id}")
async def get_external_module(module_id: str) -> Dict[str, Any]:
    """Get information about a specific external module"""
    module = await module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module with ID {module_id} not found")
    return module

@router.delete("/{module_id}")
async def deregister_external_module(module_id: str):
    """Remove an external module registration"""
    success = await module_registry.deregister_module(module_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Module with ID {module_id} not found")
    return {"message": f"Module {module_id} successfully removed from registry"}

@router.post("/{module_id}/heartbeat")
async def module_heartbeat(module_id: str):
    """Update external module activity status (heartbeat)"""
    success = await module_registry.update_module_heartbeat(module_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Module with ID {module_id} not found")
    return {"status": "ok"}

@router.get("/{module_id}/files")
async def get_module_files(
    module_id: str, 
    file_ids: List[str] = Query(...),
    background_tasks: BackgroundTasks = None
):
    """Get files for external module processing"""
    module = await module_registry.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"Module with ID {module_id} not found")
    
    if module["status"] != ModuleStatus.ACTIVE:
        raise HTTPException(status_code=400, detail=f"Module {module_id} is not active")
    
    files = []
    for file_id in file_ids:
        file_info = await storage.get_scan_status(file_id)
        if not file_info:
            logger.warning(f"File not found: {file_id}")
            continue
        
        files.append(file_info)
    
    if not files:
        raise HTTPException(status_code=404, detail="No valid files found")
    
    tar_buffer = io.BytesIO()
    
    with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tar:
        for file_info in files:
            folder_path = os.path.join("/shared_data", file_info["folder_path"])
            
            if not os.path.exists(folder_path):
                logger.warning(f"Folder not found: {folder_path}")
                continue
            
            base_path = ""
            if len(files) == 1:
                base_path = os.path.basename(folder_path)
            
            for root, dirs, files_in_dir in os.walk(folder_path):
                for file_name in files_in_dir:
                    full_path = os.path.join(root, file_name)
                    
                    rel_path = os.path.relpath(full_path, "/shared_data")
                    
                    if len(files) == 1:
                        parts = rel_path.split('/', 1)
                        if len(parts) > 1:
                            archive_path = parts[1]
                        else:
                            archive_path = os.path.basename(rel_path)
                    else:
                        archive_path = rel_path
                    
                    try:
                        tar.add(full_path, arcname=archive_path)
                    except Exception as e:
                        logger.warning(f"Couldn't add file {full_path} to tar: {e}")
    
    tar_buffer.seek(0)
    tar_data = tar_buffer.getvalue()
    
    await module_registry.update_module_heartbeat(module_id)
    
    return StreamingResponse(
        io.BytesIO(tar_data),
        media_type="application/x-tar",
        headers={"Content-Disposition": f"attachment; filename=app_files.tar.gz"}
    )

