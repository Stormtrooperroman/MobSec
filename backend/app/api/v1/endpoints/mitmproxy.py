from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request, Query
from fastapi.responses import Response, FileResponse, JSONResponse
from typing import List, Optional, Dict, Any
import json
import logging
from io import BytesIO
import hashlib
import re
import tempfile
import os
from app.dynamic.mitmproxy_manager import MitmproxyManager, get_mitmproxy_manager
import time

router = APIRouter()

logger = logging.getLogger(__name__)


async def get_mitmproxy_manager_dependency(
    device_id: str = Query(...),
) -> MitmproxyManager:
    """Get MitmproxyManager instance for device"""
    try:
        return await get_mitmproxy_manager(device_id)
    except Exception as e:
        logger.error(f"Error getting mitmproxy manager: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get mitmproxy manager: {str(e)}"
        )


# Helper functions from the original code
def cert_to_json(certs) -> dict | None:
    """Convert certificate to JSON format"""
    if not certs:
        return None
    cert = certs[0]
    return {
        "keyinfo": cert.keyinfo,
        "sha256": cert.fingerprint().hex(),
        "notbefore": int(cert.notbefore.timestamp()),
        "notafter": int(cert.notafter.timestamp()),
        "serial": str(cert.serial),
        "subject": cert.subject,
        "issuer": cert.issuer,
        "altnames": [str(x.value) for x in cert.altnames],
    }


def flow_to_json(flow) -> dict:
    """Convert mitmproxy flow to JSON format"""
    f = {
        "id": flow.id,
        "intercepted": flow.intercepted,
        "is_replay": flow.is_replay,
        "type": flow.type,
        "modified": flow.modified(),
        "marked": flow.marked,
        "comment": flow.comment,
        "timestamp_created": flow.timestamp_created,
    }

    # Add client connection info
    if flow.client_conn:
        f["client_conn"] = {
            "id": flow.client_conn.id,
            "peername": flow.client_conn.peername,
            "sockname": flow.client_conn.sockname,
            "tls_established": flow.client_conn.tls_established,
            "cert": cert_to_json(flow.client_conn.certificate_list),
            "sni": flow.client_conn.sni,
            "cipher": flow.client_conn.cipher,
            "timestamp_start": flow.client_conn.timestamp_start,
            "timestamp_end": flow.client_conn.timestamp_end,
        }

    # Add server connection info
    if flow.server_conn:
        f["server_conn"] = {
            "id": flow.server_conn.id,
            "peername": flow.server_conn.peername,
            "sockname": flow.server_conn.sockname,
            "address": flow.server_conn.address,
            "tls_established": flow.server_conn.tls_established,
            "cert": cert_to_json(flow.server_conn.certificate_list),
            "sni": flow.server_conn.sni,
            "cipher": flow.server_conn.cipher,
            "timestamp_start": flow.server_conn.timestamp_start,
            "timestamp_end": flow.server_conn.timestamp_end,
        }

    # Add error info
    if flow.error:
        f["error"] = flow.error.get_state()

    # Handle HTTP flows
    if hasattr(flow, "request") and flow.request:
        content_length = (
            len(flow.request.raw_content) if flow.request.raw_content else None
        )
        content_hash = (
            hashlib.sha256(flow.request.raw_content).hexdigest()
            if flow.request.raw_content
            else None
        )

        f["request"] = {
            "method": flow.request.method,
            "scheme": flow.request.scheme,
            "host": flow.request.host,
            "port": flow.request.port,
            "path": flow.request.path,
            "http_version": flow.request.http_version,
            "headers": list(flow.request.headers.items()),
            "contentLength": content_length,
            "contentHash": content_hash,
            "timestamp_start": flow.request.timestamp_start,
            "timestamp_end": flow.request.timestamp_end,
            "pretty_host": flow.request.pretty_host,
        }

        if flow.response:
            content_length = (
                len(flow.response.raw_content) if flow.response.raw_content else None
            )
            content_hash = (
                hashlib.sha256(flow.response.raw_content).hexdigest()
                if flow.response.raw_content
                else None
            )

            f["response"] = {
                "http_version": flow.response.http_version,
                "status_code": flow.response.status_code,
                "reason": flow.response.reason,
                "headers": list(flow.response.headers.items()),
                "contentLength": content_length,
                "contentHash": content_hash,
                "timestamp_start": flow.response.timestamp_start,
                "timestamp_end": flow.response.timestamp_end,
            }

    return f


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
        logger.error(f"Error getting flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flows/dump")
async def dump_flows(
    request: Request,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Download flows as binary dump or HAR format"""
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
                }
            )
        else:
            # Create binary dump (default behavior)
            dump_content = manager.export_flows_to_dump(flows)

            # Create temporary file for response
            with tempfile.NamedTemporaryFile(delete=False, suffix=".dump") as tmp_file:
                tmp_file.write(dump_content)
                tmp_file_path = tmp_file.name

            # Return file response and schedule cleanup
            def cleanup():
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass

            return FileResponse(
                path=tmp_file_path,
                filename="flows.dump",
                media_type="application/octet-stream",
                background=cleanup,
            )
    except Exception as e:
        logger.error(f"Error dumping flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        else:
            raise HTTPException(status_code=400, detail="Failed to load flows")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flows/clear")
async def clear_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Clear all flows"""
    try:
        success = manager.clear_flows()
        if success:
            return {"message": "Flows cleared successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to clear flows")
    except Exception as e:
        logger.error(f"Error clearing flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flows/resume")
async def resume_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Resume all intercepted flows"""
    try:
        resumed_count = manager.resume_all_flows()
        return {"message": f"Resumed {resumed_count} flows"}
    except Exception as e:
        logger.error(f"Error resuming flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flows/kill")
async def kill_flows(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Kill all killable flows"""
    try:
        killed_count = manager.kill_all_flows()
        return {"message": f"Killed {killed_count} flows"}
    except Exception as e:
        logger.error(f"Error killing flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error getting flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/flows/{flow_id}", response_model=Dict[str, Any])
async def update_flow(
    flow_id: str,
    request: Request,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Update flow data"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        data = await request.json()
        if not data:
            raise HTTPException(status_code=400, detail="No JSON data provided")

        # Backup flow before modification
        flow.backup()

        try:
            # Update flow based on provided data
            for key, value in data.items():
                if key == "request" and hasattr(flow, "request"):
                    for req_key, req_value in value.items():
                        if req_key in [
                            "method",
                            "scheme",
                            "host",
                            "path",
                            "http_version",
                        ]:
                            setattr(flow.request, req_key, str(req_value))
                        elif req_key == "port":
                            flow.request.port = int(req_value)
                        elif req_key == "headers":
                            flow.request.headers.clear()
                            for header in req_value:
                                flow.request.headers.add(*header)
                        elif req_key == "content":
                            flow.request.text = req_value

                elif key == "response" and hasattr(flow, "response") and flow.response:
                    for resp_key, resp_value in value.items():
                        if resp_key in ["http_version"]:
                            setattr(flow.response, resp_key, str(resp_value))
                        elif resp_key == "status_code":
                            flow.response.status_code = int(resp_value)
                        elif resp_key == "headers":
                            flow.response.headers.clear()
                            for header in resp_value:
                                flow.response.headers.add(*header)
                        elif resp_key == "content":
                            flow.response.text = resp_value

                elif key == "marked":
                    flow.marked = value
                elif key == "comment":
                    flow.comment = value

            manager.update_flow(flow)
            return flow_to_json(flow)

        except Exception as update_error:
            flow.revert()
            raise update_error

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        else:
            raise HTTPException(status_code=500, detail="Failed to delete flow")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error resuming flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        else:
            raise HTTPException(status_code=400, detail="Flow is not killable")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error killing flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flows/{flow_id}/duplicate")
async def duplicate_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Duplicate a flow"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        new_flow = flow.copy()
        success = manager.add_flow(new_flow)
        if success:
            return {"id": new_flow.id, "message": "Flow duplicated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to duplicate flow")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error duplicating flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flows/{flow_id}/replay")
async def replay_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Replay a flow"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        success = manager.replay_flow(flow)
        if success:
            return {"message": "Flow replay initiated"}
        else:
            raise HTTPException(status_code=500, detail="Failed to replay flow")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error replaying flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/flows/{flow_id}/revert")
async def revert_flow(
    flow_id: str, manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency)
):
    """Revert flow modifications"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if flow.modified():
            flow.revert()
            manager.update_flow(flow)
            return {"message": "Flow reverted successfully"}
        else:
            return {"message": "Flow has no modifications to revert"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reverting flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/flows/{flow_id}/{message}/content/{content_view}")
async def get_flow_content(
    flow_id: str,
    message: str,
    content_view: str,
    request: Request,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get flow content (request/response) with specified view"""
    try:
        flow = manager.get_flow_by_id(flow_id)
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if message not in ["request", "response"]:
            raise HTTPException(status_code=400, detail="Invalid message type")

        if content_view not in ["auto", "text", "hex", "raw"]:
            raise HTTPException(status_code=400, detail="Invalid content view")

        msg_obj = getattr(flow, message, None)
        if not msg_obj:
            raise HTTPException(status_code=404, detail=f"Flow has no {message}")

        # Get content based on view type
        if content_view == "auto":
            # Try to get text content first, fallback to hex
            try:
                content = msg_obj.get_text(strict=False)
                if content is None:
                    content = msg_obj.get_content(strict=False)
                    if content:
                        # Convert to hex if binary
                        content = content.hex()
            except:
                content = msg_obj.get_content(strict=False)
                if content:
                    content = content.hex()
        elif content_view == "text":
            content = msg_obj.get_text(strict=False)
            if content is None:
                content = "Content is not text"
        elif content_view == "hex":
            content = msg_obj.get_content(strict=False)
            if content:
                content = content.hex()
            else:
                content = ""
        else:  # raw
            content = msg_obj.get_content(strict=False)

        # Determine content type
        if content_view == "hex":
            media_type = "text/plain"
        elif content_view == "text":
            media_type = "text/plain"
        else:
            media_type = "application/octet-stream"

        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={message}_content_{content_view}"
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error getting flow content {flow_id}/{message}/{content_view}: {e}"
        )
        raise HTTPException(status_code=500, detail=str(e))


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
        logger.error(f"Error getting flow content {flow_id}/{message}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        else:
            raise HTTPException(status_code=500, detail="Failed to update flow content")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting flow content {flow_id}/{message}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/options", response_model=Dict[str, Any])
async def get_options(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get mitmproxy options"""
    try:
        options = manager.get_options()
        return options
    except Exception as e:
        logger.error(f"Error getting options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/options")
async def update_options(
    request: Request,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Update mitmproxy options"""
    try:
        data = await request.json()
        if not data:
            raise HTTPException(status_code=400, detail="No JSON data provided")

        success = manager.update_options(data)
        if success:
            return {"message": "Options updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update options")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating options: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state", response_model=Dict[str, Any])
async def get_state(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get mitmproxy state information"""
    try:
        state = manager.get_state()
        return state
    except Exception as e:
        logger.error(f"Error getting state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/commands", response_model=Dict[str, Any])
async def get_commands(
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Get available commands"""
    try:
        commands = manager.get_commands()
        return commands
    except Exception as e:
        logger.error(f"Error getting commands: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/commands/{cmd}")
async def execute_command(
    cmd: str,
    request: Request,
    manager: MitmproxyManager = Depends(get_mitmproxy_manager_dependency),
):
    """Execute a command"""
    try:
        try:
            data = await request.json()
        except:
            data = {}

        args = data.get("arguments", [])

        result = manager.execute_command(cmd, args)
        return {"value": result}
    except Exception as e:
        logger.error(f"Error executing command {cmd}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
