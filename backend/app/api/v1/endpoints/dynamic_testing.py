from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Query,
    UploadFile,
    File,
)
from typing import List, Dict, Optional
from app.dynamic.device_manager import DeviceManager
from app.dynamic.websocket_manager import WebSocketManager
from app.dynamic.remote_shell import RemoteShell
from app.dynamic.file_manager import FileManager
from app.dynamic.frida_manager import FridaManager
import logging
import tempfile
import os
import subprocess

router = APIRouter()
websocket_manager = WebSocketManager()
logger = logging.getLogger(__name__)


@router.get("/devices")
async def get_devices() -> List[Dict[str, str]]:
    """
    Returns a list of available Android devices (both physical and emulated)
    """
    devices = []

    # Get all devices from DeviceManager (includes both physical and emulated)
    try:
        device_manager = DeviceManager()
        devices = await device_manager.get_devices()
    except Exception as e:
        logger.error(f"Error getting devices: {str(e)}")

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
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/{device_id}")
async def websocket_endpoint(
    websocket: WebSocket, device_id: str, action: Optional[str] = Query(None)
):
    """
    Main WebSocket endpoint for interacting with the device
    """
    try:
        device_manager = DeviceManager()
        device = await device_manager.get_device(device_id)

        if not device:
            await websocket.close(code=4004, reason="Device not found")
            return

        await websocket.accept()
        logger.info(
            f"WebSocket connection accepted for device '{device_id}' (len: {len(device_id)}) with action {action}"
        )

        if action == "stream":
            logger.info(f"Connecting stream for device '{device_id}'")
            await websocket_manager.connect(websocket, device_id)

            while True:
                try:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    elif message["type"] == "websocket.receive":
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
                        f"Error handling message for device {device_id}: {str(e)}"
                    )
                    break

        elif action == "shell":
            logger.info(f"Starting shell session for device {device_id}")
            shell = RemoteShell(websocket, device_id)
            if not await shell.start():
                logger.error(f"Failed to start shell for device {device_id}")
                await websocket.close(code=4000, reason="Failed to start shell")
                return

            logger.info(
                f"Shell started successfully for device {device_id}, waiting for messages..."
            )

            try:
                while True:
                    try:
                        message = await websocket.receive()
                        logger.info(f"Received WebSocket message: {message}")

                        if message["type"] == "websocket.disconnect":
                            logger.info("WebSocket disconnect received")
                            break
                        elif message["type"] == "websocket.receive":
                            if "bytes" in message:
                                logger.info(
                                    f"Received bytes message: {len(message['bytes'])} bytes"
                                )
                                await shell.handle_input(message["bytes"].decode())
                            elif "text" in message:
                                logger.info(f"Received text message: {message['text']}")
                                await shell.handle_input(message["text"])
                        else:
                            logger.info(f"Unknown message type: {message['type']}")
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {str(e)}")
                        break
            except WebSocketDisconnect:
                logger.info(f"Shell WebSocket disconnected for device {device_id}")
            except Exception as e:
                logger.error(f"Error in shell session: {str(e)}")
            finally:
                await shell.stop()

        elif action == "file_manager":
            logger.info(f"Starting file manager session for device {device_id}")
            file_manager = FileManager(websocket, device_id)
            if not await file_manager.start():
                logger.error(f"Failed to start file manager for device {device_id}")
                await websocket.close(code=4000, reason="Failed to start file manager")
                return

            logger.info(
                f"File manager started successfully for device {device_id}, waiting for messages..."
            )

            try:
                while True:
                    try:
                        message = await websocket.receive()
                        logger.info(f"Received WebSocket message: {message}")

                        if message["type"] == "websocket.disconnect":
                            logger.info("WebSocket disconnect received")
                            break
                        elif message["type"] == "websocket.receive":
                            if "text" in message:
                                logger.info(f"Received text message: {message['text']}")
                                await file_manager.handle_message(message["text"])
                            elif "bytes" in message:
                                logger.info(
                                    f"Received bytes message: {len(message['bytes'])} bytes"
                                )
                                pass
                        else:
                            logger.info(f"Unknown message type: {message['type']}")
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {str(e)}")
                        break
            except WebSocketDisconnect:
                logger.info(
                    f"File manager WebSocket disconnected for device {device_id}"
                )
            except Exception as e:
                logger.error(f"Error in file manager session: {str(e)}")
            finally:
                await file_manager.stop()

        elif action == "frida":
            logger.info(f"Starting Frida session for device {device_id}")
            frida_manager = FridaManager(websocket, device_id)
            if not await frida_manager.start():
                logger.error(f"Failed to start Frida manager for device {device_id}")
                await websocket.close(code=4000, reason="Failed to start Frida manager")
                return

            logger.info(
                f"Frida manager started successfully for device {device_id}, waiting for messages..."
            )

            try:
                while True:
                    try:
                        message = await websocket.receive()
                        logger.info(f"Received WebSocket message: {message}")

                        if message["type"] == "websocket.disconnect":
                            logger.info("WebSocket disconnect received")
                            break
                        elif message["type"] == "websocket.receive":
                            if "text" in message:
                                logger.info(f"Received text message: {message['text']}")
                                await frida_manager.handle_message(message["text"])
                            elif "bytes" in message:
                                logger.info(
                                    f"Received bytes message: {len(message['bytes'])} bytes"
                                )
                                pass
                        else:
                            logger.info(f"Unknown message type: {message['type']}")
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {str(e)}")
                        break
            except WebSocketDisconnect:
                logger.info(f"Frida WebSocket disconnected for device {device_id}")
            except Exception as e:
                logger.error(f"Error in Frida session: {str(e)}")
            finally:
                await frida_manager.stop()

        elif action == "multiplex":
            await websocket_manager.handle_multiplex(websocket, device_id)

    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed for device {device_id}")
        await websocket_manager.disconnect(websocket, device_id)
    except Exception as e:
        logger.error(f"Error in WebSocket endpoint for device {device_id}: {str(e)}")
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
        logger.error(f"Error in multiplex endpoint: {str(e)}")
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

        # Import storage service to get file info
        from app.core.app_manager import AsyncStorageService

        storage = AsyncStorageService()

        # Get file info
        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found in storage")

        # Verify it's an APK file
        if file_info.get("file_type") != "apk":
            raise HTTPException(status_code=400, detail="File is not an APK")

        # Build file path
        storage_dir = "/shared_data"
        folder_path = file_info.get("folder_path")
        original_name = file_info.get("original_name")

        apk_path = f"{storage_dir}/{folder_path}/{original_name}"

        # Check if file exists
        import os

        if not os.path.exists(apk_path):
            raise HTTPException(
                status_code=404, detail=f"APK file not found at: {apk_path}"
            )

        # Install APK using ADB
        import subprocess

        process = subprocess.run(
            ["adb", "-s", device_id, "install", "-r", apk_path],
            capture_output=True,
            text=True,
        )

        if process.returncode == 0:
            return {
                "status": "success",
                "message": f"Successfully installed {app_name}",
                "app_name": app_name,
                "file_hash": file_hash,
            }
        else:
            error_output = (
                process.stderr.strip() if process.stderr else process.stdout.strip()
            )
            raise HTTPException(
                status_code=500, detail=f"Failed to install {app_name}: {error_output}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing app: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error installing app: {str(e)}")


@router.post("/device/{device_id}/install-apk-direct")
async def install_apk_direct(device_id: str, apk_file: UploadFile = File(...)):
    """
    Install an APK file directly on the device without storing in database
    """
    try:
        # Validate file type
        if not apk_file.filename.lower().endswith(".apk"):
            raise HTTPException(status_code=400, detail="Only APK files are supported")

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".apk") as temp_file:
            # Write uploaded file to temporary location
            content = await apk_file.read()
            temp_file.write(content)
            temp_apk_path = temp_file.name

        try:
            # Install APK using ADB
            logger.info(f"Installing APK {apk_file.filename} on device {device_id}")

            process = subprocess.run(
                ["adb", "-s", device_id, "install", "-r", temp_apk_path],
                capture_output=True,
                text=True,
            )

            if process.returncode == 0:
                logger.info(
                    f"Successfully installed {apk_file.filename} on device {device_id}"
                )
                return {
                    "status": "success",
                    "message": f"Successfully installed {apk_file.filename}",
                    "app_name": apk_file.filename,
                }
            else:
                error_output = (
                    process.stderr.strip() if process.stderr else process.stdout.strip()
                )
                logger.error(f"Failed to install {apk_file.filename}: {error_output}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to install {apk_file.filename}: {error_output}",
                )

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_apk_path)
            except Exception as e:
                logger.warning(
                    f"Failed to cleanup temporary file {temp_apk_path}: {str(e)}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error installing APK directly: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error installing APK: {str(e)}")


@router.post("/device/{device_id}/stop")
async def stop_device_server(device_id: str):
    """
    Stops the scrcpy server on the specified device
    """
    device_manager = DeviceManager()
    success = await device_manager.stop_device_server(device_id)

    if not success:
        raise HTTPException(status_code=404, detail="Device not found")

    return {"status": "success"}
