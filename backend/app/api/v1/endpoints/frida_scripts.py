from fastapi import APIRouter, HTTPException, Depends, Request
from typing import List, Optional, Dict, Any
from app.dynamic.frida_script_service import FridaScriptService

router = APIRouter()


def get_script_service():
    return FridaScriptService()


@router.post("/scripts")
async def create_script(
    request: Request, script_service: FridaScriptService = Depends(get_script_service)
):
    """Creates a new Frida script"""
    try:
        data = await request.json()
        name = data.get("name")
        content = data.get("content")

        if not name or not content:
            raise HTTPException(status_code=400, detail="Name and content are required")

        script = await script_service.create_script(name=name, content=content)
        return script
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating script: {str(e)}")


@router.get("/scripts")
async def list_scripts(
    script_service: FridaScriptService = Depends(get_script_service),
):
    """Gets list of all scripts"""
    try:
        scripts = await script_service.list_scripts()
        return scripts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing scripts: {str(e)}")


@router.get("/scripts/{script_name}")
async def get_script(
    script_name: str, script_service: FridaScriptService = Depends(get_script_service)
):
    """Gets information about specific script"""
    try:
        script = await script_service.get_script_by_name(script_name)
        if not script:
            raise HTTPException(
                status_code=404, detail=f"Script '{script_name}' not found"
            )
        return script
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting script: {str(e)}")


@router.get("/scripts/{script_name}/content")
async def get_script_content(
    script_name: str, script_service: FridaScriptService = Depends(get_script_service)
):
    """Gets script content"""
    try:
        content = await script_service.get_script_content(script_name)
        if content is None:
            raise HTTPException(
                status_code=404, detail=f"Script '{script_name}' not found"
            )
        return {"name": script_name, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting script content: {str(e)}"
        )


@router.put("/scripts/{script_name}")
async def update_script(
    script_name: str,
    request: Request,
    script_service: FridaScriptService = Depends(get_script_service),
):
    """Updates script"""
    try:
        data = await request.json()
        content = data.get("content")

        script = await script_service.update_script(name=script_name, content=content)
        if not script:
            raise HTTPException(
                status_code=404, detail=f"Script '{script_name}' not found"
            )
        return script
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating script: {str(e)}")


@router.delete("/scripts/{script_name}")
async def delete_script(
    script_name: str, script_service: FridaScriptService = Depends(get_script_service)
):
    """Deletes script"""
    try:
        success = await script_service.delete_script(script_name)
        if not success:
            raise HTTPException(
                status_code=404, detail=f"Script '{script_name}' not found"
            )
        return {"message": f"Script '{script_name}' deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting script: {str(e)}")


@router.get("/scripts/stats")
async def get_script_stats(
    script_service: FridaScriptService = Depends(get_script_service),
):
    """Gets script statistics"""
    try:
        stats = await script_service.get_script_stats()
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting script stats: {str(e)}"
        )
