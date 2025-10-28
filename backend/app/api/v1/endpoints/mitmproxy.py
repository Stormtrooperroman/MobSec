import logging
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.dynamic.tools.mitmproxy_manager import (
    MitmproxyManager,
    flow_to_json,
    get_mitmproxy_manager,
)

router = APIRouter()

logger = logging.getLogger(__name__)


async def get_mitmproxy_manager_dependency(
    device_id: str = Query(...),
) -> MitmproxyManager:
    """Get MitmproxyManager instance for device"""
    try:
        return await get_mitmproxy_manager(device_id)
    except Exception as e:
        logger.error("Error getting mitmproxy manager: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to get mitmproxy manager: {str(e)}"
        ) from e


# API Routes


@router.get("/flows", response_model=List[Dict[str, Any]])
async def get_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get all flows"""
    try:
        flows = manager.get_flows()
        return [flow_to_json(f) for f in flows]
    except Exception as e:
        logger.error("Error getting flows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/flows/dump")
async def dump_flows(
    request: Request,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Download flows as binary dump, JSON or HAR format"""
    try:
        filter_param = request.query_params.get("filter", "")
        format_param = request.query_params.get("format", "dump")

        # Apply filter if provided
        flows = manager.get_flows()
        if filter_param:
            flows = manager.filter_flows(flows, filter_param)

        if format_param == "har":
            # Export as HAR format
            har_data = await manager.export_traffic("har")
            return JSONResponse(
                content=har_data,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=flows_{int(time.time())}.har"
                },
            )
        if format_param == "json":
            # Export as JSON format
            json_data = await manager.export_traffic("json")
            return JSONResponse(
                content=json_data,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=flows_{int(time.time())}.json"
                },
            )
        dump_content = manager.export_flows_to_dump(flows)

        # Create temporary file for response
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp_file:
            tmp_file.write(dump_content)
            tmp_file_path = tmp_file.name

        # Return file response and schedule cleanup
        def cleanup():
            try:
                os.unlink(tmp_file_path)
            except Exception:
                pass

        return FileResponse(
            path=tmp_file_path,
            filename="flows.dump",
            media_type="application/octet-stream",
            background=cleanup,
        )
    except Exception as e:
        logger.error("Error dumping flows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/dump")
async def load_flows(
    file: UploadFile = File(...),
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Load flows from uploaded dump file"""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")

        # Load flows from file
        file_content = await file.read()
        success = manager.load_flows_from_dump(file_content)

        if success:
            return {"message": "Flows loaded successfully"}
        raise HTTPException(status_code=400, detail="Failed to load flows")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error loading flows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/clear")
async def clear_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Clear all flows"""
    try:
        success = manager.clear_flows()
        if success:
            return {"message": "Flows cleared successfully"}
        raise HTTPException(status_code=500, detail="Failed to clear flows")
    except Exception as e:
        logger.error("Error clearing flows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/resume")
async def resume_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Resume all intercepted flows"""
    try:
        resumed_count = manager.resume_all_flows()
        return {"message": f"Resumed {resumed_count} flows"}
    except Exception as e:
        logger.error("Error resuming flows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/kill")
async def kill_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Kill all killable flows"""
    try:
        killed_count = manager.kill_all_flows()
        return {"message": f"Killed {killed_count} flows"}
    except Exception as e:
        logger.error("Error killing flows: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/flows/{flow_id}", response_model=Dict[str, Any])
async def get_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Get specific flow by ID"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")
        return flow_to_json(flow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting flow %s: %s", flow_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/flows/{flow_id}")
async def delete_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Delete a flow"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if hasattr(flow, "killable") and flow.killable:
            flow.kill()

        success = manager.delete_flow(flow_id)
        if success:
            return {"message": "Flow deleted successfully"}
        raise HTTPException(status_code=500, detail="Failed to delete flow")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error deleting flow %s: %s", flow_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/{flow_id}/resume")
async def resume_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Resume a specific flow"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        flow.resume()
        manager.update_flow(flow)
        return {"message": "Flow resumed successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resuming flow %s: %s", flow_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/{flow_id}/kill")
async def kill_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Kill a specific flow"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if hasattr(flow, "killable") and flow.killable:
            flow.kill()
            manager.update_flow(flow)
            return {"message": "Flow killed successfully"}
        raise HTTPException(status_code=400, detail="Flow is not killable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error killing flow %s: %s", flow_id, e)
        raise HTTPException(status_code=500, detail=str(e)) from e



def _get_content_by_view(msg_obj, content_view: str):
    """Get content from message object based on view type"""
    try:
        if content_view == "auto":
            # Try to get text content first, fallback to hex
            try:
                content = msg_obj.get_text(strict=False)
                if content:
                    return content
            except Exception:
                pass
            # Fallback to hex
            content = msg_obj.get_content(strict=False)
            if content:
                return content.hex()
            return ""
        if content_view == "text":
            content = msg_obj.get_text(strict=False)
            return content if content else "Content is not text"
        if content_view == "hex":
            content = msg_obj.get_content(strict=False)
            if content:
                return content.hex()
            return ""
        # raw
        content = msg_obj.get_content(strict=False)
        return content if content is not None else b""
    except Exception as e:
        logger.warning("Error getting content by view: %s", e)
        return ""


def _get_media_type(content_view: str) -> str:
    """Determine media type based on content view"""
    if content_view in ["hex", "text"]:
        return "text/plain"
    return "application/octet-stream"


@router.get("/flows/{flow_id}/{message}/content/{content_view}")
async def get_flow_content(
    flow_id: str,
    message: str,
    content_view: str,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get flow content (request/response) with specified view"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            logger.warning("Flow not found: %s", flow_id)
            raise HTTPException(status_code=404, detail="Flow not found")

        if message not in ["request", "response"]:
            logger.warning("Invalid message type: %s", message)
            raise HTTPException(status_code=400, detail="Invalid message type")

        if content_view not in ["auto", "text", "hex", "raw"]:
            logger.warning("Invalid content view: %s", content_view)
            raise HTTPException(status_code=400, detail="Invalid content view")

        msg_obj = getattr(flow, message, None)
        if not msg_obj:
            logger.warning("Message object not found: flow_id=%s, message=%s", flow_id, message)
            raise HTTPException(status_code=404, detail=f"Flow has no {message}")

        # Get content based on view type
        content = _get_content_by_view(msg_obj, content_view)
        media_type = _get_media_type(content_view)

        # Handle different content types
        if content is None:
            content = b"" if content_view == "raw" else ""

        if content_view == "raw" and isinstance(content, bytes):
            return Response(
                content=content,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename={message}_content_{content_view}"
                },
            )
        return Response(
            content=content or "",
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={message}_content_{content_view}"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error getting flow content %s/%s/%s: %s", flow_id, message, content_view, e
        )
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/flows/{flow_id}/{message}/content")
async def get_flow_content_legacy(
    flow_id: str,
    message: str,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get flow content (request/response) - legacy endpoint"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if message not in ["request", "response"]:
            raise HTTPException(status_code=400, detail="Invalid message type")

        msg_obj = getattr(flow, message, None)
        if not msg_obj:
            raise HTTPException(status_code=404, detail=f"Flow has no {message}")

        content = msg_obj.get_content(strict=False)

        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f"attachment; filename={message}_content"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting flow content %s/%s: %s", flow_id, message, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/flows/{flow_id}/{message}/content")
async def set_flow_content(
    flow_id: str,
    message: str,
    request: Request,
    file: Optional[UploadFile] = File(None),
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Set flow content (request/response)"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if message not in ["request", "response"]:
            raise HTTPException(status_code=400, detail="Invalid message type")

        msg_obj = getattr(flow, message, None)
        if not msg_obj:
            raise HTTPException(status_code=404, detail=f"Flow has no {message}")

        # Backup flow before modification
        flow.backup()

        # Get content from uploaded file or request body
        if file:
            content = await file.read()
        else:
            content = await request.body()

        msg_obj.content = content
        success = manager.update_flow(flow)

        if success:
            return {"message": f"Flow {message} content updated successfully"}
        raise HTTPException(status_code=500, detail="Failed to update flow content")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error setting flow content %s/%s: %s", flow_id, message, e)
        raise HTTPException(status_code=500, detail=str(e)) from e


