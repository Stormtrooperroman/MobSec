import json
import logging
import os
import tempfile
from typing import Dict, List, Optional

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from app.core.app_manager import AsyncStorageService
from app.modules.module_manager import ModuleManager
from app.dynamic.communication.websocket_manager import WebSocketManager
from app.dynamic.device_management.device_manager import DeviceManager
from app.dynamic.tools.file_manager import FileManager
from app.dynamic.tools.remote_shell import RemoteShell
from app.dynamic.utils.app_installer import AppInstaller

router = APIRouter()
websocket_manager = WebSocketManager()
logger = logging.getLogger(__name__)


@router.get("/devices")
async def get_devices() -> List[Dict[str, str]]:
    """
    Returns a list of available Android devices (both physical and emulated)
    """
    devices = []

    try:
        device_manager = DeviceManager()
        devices = await device_manager.get_devices()
    except Exception as e:
        logger.error("Error getting devices: %s", str(e))

    return devices


@router.post("/device/{device_id}/start")
async def start_device_server(device_id: str):
    """
    Starts the scrcpy server on the specified device
    """
    device_manager = DeviceManager()
    device = await device_manager.get_device(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        result = await device.start_server()
        if result is None:
            raise HTTPException(status_code=500, detail="Failed to start device server")
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.websocket("/ws/{device_id}")
async def websocket_endpoint(
    websocket: WebSocket, device_id: str, action: Optional[str] = Query(None)
):
    """
    Main WebSocket endpoint for interacting with the device
    """
    module_manager = ModuleManager.get_instance()
    if action in module_manager.ACTION_MODULE_MAP:
        module_name = module_manager.ACTION_MODULE_MAP[action]
        
        exists = await module_manager.check_module_exists(module_name)

        if not exists:
            await websocket.close(code=4004, reason="Module not found")
            return

        query_params = dict(websocket.query_params)
        await module_manager.proxy_websocket(
            websocket=websocket,
            module_name=module_name,
            device_id=device_id,
            query_params=query_params,
        )
        return

    try:
        device_manager = DeviceManager()
        device = await device_manager.get_device(device_id)

        if not device:
            await websocket.close(code=4004, reason="Device not found")
            return

        await websocket.accept()
        logger.info(
            "WebSocket connection accepted for device '%s' (len: %s) with action %s",
            device_id,
            len(device_id),
            action,
        )

        if action == "stream":
            logger.info("Connecting stream for device '%s'", device_id)
            await websocket_manager.connect(websocket, device_id)

            while True:
                try:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message["type"] == "websocket.receive":
                        if "bytes" in message:
                            await websocket_manager.handle_binary_message(
                                websocket, device_id, message["bytes"]
                            )
                        elif "text" in message:
                            await websocket_manager.handle_websocket_message(
                                websocket, device_id, message["text"]
                            )
                except Exception as e:
                    logger.error(
                        "Error handling message for device %s: %s", device_id, str(e)
                    )
                    break

        elif action == "shell":
            logger.info("Starting shell session for device %s", device_id)
            shell = RemoteShell(websocket, device_id)
            if not await shell.start():
                logger.error("Failed to start shell for device %s", device_id)
                await websocket.close(code=4000, reason="Failed to start shell")
                return

            logger.info(
                "Shell started successfully for device %s, waiting for messages...", device_id
            )

            try:
                while True:
                    try:
                        message = await websocket.receive()
                        logger.info("Received WebSocket message: %s", message)

                        if message["type"] == "websocket.disconnect":
                            logger.info("WebSocket disconnect received")
                            break
                        if message["type"] == "websocket.receive":
                            if "bytes" in message:
                                logger.info(
                                    "Received bytes message: %s bytes", len(message['bytes'])
                                )
                                try:
                                    decoded_data = message["bytes"].decode(
                                        "utf-8", errors="replace"
                                    )
                                    await shell.handle_input(decoded_data)
                                except Exception as e:
                                    logger.error(
                                        "Error decoding bytes message: %s", str(e)
                                    )
                            elif "text" in message:
                                logger.info(
                                    "Received text message: %s", message["text"]
                                )
                                await shell.handle_input(message["text"])
                        else:
                            logger.info("Unknown message type: %s", message["type"])
                    except Exception as e:
                        logger.error("Error processing WebSocket message: %s", str(e))
                        break
            except WebSocketDisconnect:
                logger.info("Shell WebSocket disconnected for device %s", device_id)
            except Exception as e:
                logger.error("Error in shell session: %s", str(e))
            finally:
                await shell.stop()

        elif action == "file_manager":
            logger.info("Starting file manager session for device %s", device_id)
            file_manager = FileManager(websocket, device_id)
            if not await file_manager.start():
                logger.error("Failed to start file manager for device %s", device_id)
                await websocket.close(code=4000, reason="Failed to start file manager")
                return

            logger.info(
                "File manager started successfully for device %s, waiting for messages...",
                device_id,
            )

            try:
                while True:
                    try:
                        message = await websocket.receive()
                        logger.info("Received WebSocket message: %s", message)

                        if message["type"] == "websocket.disconnect":
                            logger.info("WebSocket disconnect received")
                            break
                        if message["type"] == "websocket.receive":
                            if "text" in message:
                                logger.info(
                                    "Received text message: %s", message["text"]
                                )
                                await file_manager.handle_message(message["text"])
                            elif "bytes" in message:
                                logger.info(
                                    "Received bytes message: %s bytes", len(message["bytes"])
                                )
                        else:
                            logger.info("Unknown message type: %s", message["type"])
                    except Exception as e:
                        logger.error("Error processing WebSocket message: %s", str(e))
                        break
            except WebSocketDisconnect:
                logger.info(
                    "File manager WebSocket disconnected for device %s", device_id
                )
            except Exception as e:
                logger.error("Error in file manager session: %s", str(e))
            finally:
                await file_manager.stop()

        elif action == "multiplex":
            await websocket_manager.handle_multiplex(websocket, device_id)

    except WebSocketDisconnect:
        logger.info("WebSocket connection closed for device %s", device_id)
        await websocket_manager.disconnect(websocket, device_id)
    except Exception as e:
        logger.error("Error in WebSocket endpoint for device %s: %s", device_id, str(e))
        await websocket_manager.disconnect(websocket, device_id)
        try:
            await websocket.close(code=4000, reason=str(e))
        except Exception:
            pass


@router.websocket("/ws")
async def multiplex_endpoint(websocket: WebSocket, action: Optional[str] = Query(None)):
    """
    WebSocket endpoint for multiplexing
    """
    try:
        if action != "multiplex":
            await websocket.close(code=4003, reason="Invalid action")
            return

        await websocket.accept()
        logger.info("Multiplex WebSocket connection accepted")

        await websocket_manager.handle_multiplex_simple(websocket)

    except WebSocketDisconnect:
        logger.info("Multiplex WebSocket connection closed")
    except Exception as e:
        logger.error("Error in multiplex endpoint: %s", str(e))
        try:
            await websocket.close(code=4000, reason=str(e))
        except Exception:
            pass


@router.post("/device/{device_id}/install-app")
async def install_app_on_device(device_id: str, request: dict):
    """
    Install an APK file on the specified device
    """
    try:
        file_hash = request.get("file_hash")
        app_name = request.get("app_name")

        if not file_hash or not app_name:
            raise HTTPException(
                status_code=400, detail="file_hash and app_name are required"
            )

        storage = AsyncStorageService()

        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found in storage")

        if file_info.get("file_type") != "apk":
            raise HTTPException(status_code=400, detail="File is not an APK")

        storage_dir = "/shared_data"
        folder_path = file_info.get("folder_path")
        original_name = file_info.get("original_name")

        apk_path = f"{storage_dir}/{folder_path}/{original_name}"

        if not os.path.exists(apk_path):
            raise HTTPException(
                status_code=404, detail=f"APK file not found at: {apk_path}"
            )

        success, message = await AppInstaller.install_apk(device_id, apk_path)

        if success:
            return {
                "status": "success",
                "message": message,
                "app_name": app_name,
                "file_hash": file_hash,
            }

        raise HTTPException(status_code=500, detail=message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error installing app: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error installing app: {str(e)}") from e


@router.post("/device/{device_id}/install-apk-direct")
async def install_apk_direct(device_id: str, apk_file: UploadFile = File(...)):
    """
    Install an APK file directly on the device without storing in database
    """
    try:
        if not apk_file.filename.lower().endswith(".apk"):
            raise HTTPException(status_code=400, detail="Only APK files are supported")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".apk") as temp_file:
            content = await apk_file.read()
            temp_file.write(content)
            temp_apk_path = temp_file.name

        try:
            logger.info("Installing APK %s on device %s", apk_file.filename, device_id)

            success, message = await AppInstaller.install_apk(device_id, temp_apk_path)

            if success:
                logger.info(
                    "Successfully installed %s on device %s", apk_file.filename, device_id
                )
                return {
                    "status": "success",
                    "message": message,
                    "app_name": apk_file.filename,
                }

            logger.error("Failed to install %s: %s", apk_file.filename, message)
            raise HTTPException(
                status_code=500,
                detail=message,
            )

        finally:
            try:
                os.unlink(temp_apk_path)
            except Exception as e:
                logger.warning(
                    "Failed to cleanup temporary file %s: %s", temp_apk_path, str(e)
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error installing APK directly: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error installing APK: {str(e)}") from e


# Physical Device Management Endpoints


@router.post("/device/{device_id}/enable-wireless")
async def enable_wireless_debugging(device_id: str):
    """Enable wireless debugging on a USB-connected device"""
    try:
        device_manager = DeviceManager()
        success = await device_manager.enable_wireless_debugging(device_id)

        if success:
            return {
                "status": "success",
                "message": "Wireless debugging enabled successfully",
                "data": {"wireless_enabled": True},
            }

        raise HTTPException(
            status_code=500, detail="Failed to enable wireless debugging"
        )

    except Exception as e:
        logger.error("Error enabling wireless debugging: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error enabling wireless debugging: {str(e)}"
        ) from e


@router.post("/device/connect-wifi")
async def connect_wifi_device(request: dict):
    """Connect to a device via WiFi"""
    try:
        ip_address = request.get("ip_address")
        port = request.get("port", 5555)

        if not ip_address:
            raise HTTPException(status_code=400, detail="ip_address is required")

        device_manager = DeviceManager()
        success = await device_manager.connect_wifi_device(ip_address, port)

        if success:
            return {
                "status": "success",
                "message": f"Successfully connected to device at {ip_address}:{port}",
                "data": {"ip_address": ip_address, "port": port, "connected": True},
            }

        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to device at {ip_address}:{port}",
        )

    except Exception as e:
        logger.error("Error connecting to WiFi device: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error connecting to WiFi device: {str(e)}"
        ) from e
