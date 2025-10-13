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
from app.dynamic.mitmproxy_manager import MitmproxyManager, get_mitmproxy_manager
import logging
import tempfile
import os
import subprocess
import time

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
                                try:
                                    # Декодируем с явным указанием кодировки и обработкой ошибок
                                    decoded_data = message["bytes"].decode(
                                        "utf-8", errors="replace"
                                    )
                                    await shell.handle_input(decoded_data)
                                except Exception as e:
                                    logger.error(
                                        f"Error decoding bytes message: {str(e)}"
                                    )
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

        elif action == "mitmproxy":
            logger.info(f"Starting Mitmproxy session for device {device_id}")
            mitmproxy_manager = await get_mitmproxy_manager(device_id)

            # Регистрируем WebSocket для получения событий в реальном времени
            mitmproxy_manager.add_websocket(websocket)

            if not await mitmproxy_manager.start():
                logger.error(
                    f"Failed to start Mitmproxy manager for device {device_id}"
                )
                mitmproxy_manager.remove_websocket(websocket)
                await websocket.close(
                    code=4000, reason="Failed to start Mitmproxy manager"
                )
                return

            logger.info(
                f"Mitmproxy manager started successfully for device {device_id}, waiting for messages..."
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
                                try:
                                    # Парсим JSON сообщение
                                    import json

                                    data = json.loads(message["text"])

                                    # Добавляем device_id к сообщению если его нет
                                    if "device_id" not in data:
                                        data["device_id"] = device_id

                                    # Передаем обновленное сообщение в mitmproxy_manager
                                    await mitmproxy_manager.handle_message(
                                        websocket, json.dumps(data)
                                    )
                                except json.JSONDecodeError:
                                    logger.error(
                                        f"Invalid JSON message: {message['text']}"
                                    )
                                    await websocket.send_text(
                                        json.dumps(
                                            {
                                                "type": "mitmproxy",
                                                "action": "error",
                                                "message": "Invalid JSON format",
                                            }
                                        )
                                    )
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
                logger.info(f"Mitmproxy WebSocket disconnected for device {device_id}")
            except Exception as e:
                logger.error(f"Error in Mitmproxy session: {str(e)}")
            finally:
                # Удаляем WebSocket из регистрации
                mitmproxy_manager.remove_websocket(websocket)
                await mitmproxy_manager.stop()

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

        from app.core.app_manager import AsyncStorageService

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
        if not apk_file.filename.lower().endswith(".apk"):
            raise HTTPException(status_code=400, detail="Only APK files are supported")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".apk") as temp_file:
            content = await apk_file.read()
            temp_file.write(content)
            temp_apk_path = temp_file.name

        try:
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


# Global storage for mitmproxy managers to maintain state
_mitmproxy_managers = {}

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
                "data": {"wireless_enabled": True}
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail="Failed to enable wireless debugging"
            )
            
    except Exception as e:
        logger.error(f"Error enabling wireless debugging: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error enabling wireless debugging: {str(e)}"
        )


@router.post("/device/connect-wifi")
async def connect_wifi_device(request: dict):
    """Connect to a device via WiFi"""
    try:
        ip_address = request.get("ip_address")
        port = request.get("port", 5555)
        
        if not ip_address:
            raise HTTPException(
                status_code=400, 
                detail="ip_address is required"
            )
        
        device_manager = DeviceManager()
        success = await device_manager.connect_wifi_device(ip_address, port)
        
        if success:
            return {
                "status": "success",
                "message": f"Successfully connected to device at {ip_address}:{port}",
                "data": {
                    "ip_address": ip_address,
                    "port": port,
                    "connected": True
                }
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to connect to device at {ip_address}:{port}"
            )
            
    except Exception as e:
        logger.error(f"Error connecting to WiFi device: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error connecting to WiFi device: {str(e)}"
        )


@router.post("/device/disconnect-wifi")
async def disconnect_wifi_device(request: dict):
    """Disconnect from a WiFi device"""
    try:
        ip_address = request.get("ip_address")
        port = request.get("port", 5555)
        
        if not ip_address:
            raise HTTPException(
                status_code=400, 
                detail="ip_address is required"
            )
        
        device_manager = DeviceManager()
        success = await device_manager.disconnect_wifi_device(ip_address, port)
        
        if success:
            return {
                "status": "success",
                "message": f"Successfully disconnected from device at {ip_address}:{port}",
                "data": {
                    "ip_address": ip_address,
                    "port": port,
                    "connected": False
                }
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to disconnect from device at {ip_address}:{port}"
            )
            
    except Exception as e:
        logger.error(f"Error disconnecting from WiFi device: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error disconnecting from WiFi device: {str(e)}"
        )


@router.get("/device/{device_id}/properties")
async def get_device_properties(device_id: str):
    """Get detailed properties of a device"""
    try:
        device_manager = DeviceManager()
        properties = await device_manager.get_device_properties(device_id)
        
        return {
            "status": "success",
            "data": {
                "device_id": device_id,
                "properties": properties
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting device properties: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error getting device properties: {str(e)}"
        )


@router.get("/device/{device_id}/screen-info")
async def get_device_screen_info(device_id: str):
    """Get device screen dimensions"""
    try:
        device_manager = DeviceManager()
        screen_info = await device_manager.get_device_screen_info(device_id)
        
        if screen_info:
            return {
                "status": "success",
                "data": {
                    "device_id": device_id,
                    "screen_info": screen_info
                }
            }
        else:
            raise HTTPException(
                status_code=404, 
                detail="Screen information not available for this device"
            )
        
    except Exception as e:
        logger.error(f"Error getting device screen info: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error getting device screen info: {str(e)}"
        )


@router.get("/device/{device_id}/connectivity")
async def check_device_connectivity(device_id: str):
    """Check if a device is still connected and responsive"""
    try:
        device_manager = DeviceManager()
        is_connected = await device_manager.check_device_connectivity(device_id)
        
        return {
            "status": "success",
            "data": {
                "device_id": device_id,
                "connected": is_connected
            }
        }
        
    except Exception as e:
        logger.error(f"Error checking device connectivity: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error checking device connectivity: {str(e)}"
        )


# Mitmproxy HTTP API Endpoints


@router.get("/device/{device_id}/mitmproxy/status")
async def get_mitmproxy_status(device_id: str):
    """Get mitmproxy status for a device"""
    try:
        # Проверяем существующий менеджер
        if device_id in _mitmproxy_managers:
            manager = _mitmproxy_managers[device_id]
            proxy_running = (
                manager.proxy_task is not None
                and not manager.proxy_task.done()
                and not getattr(manager.proxy_task, "error", None)
            )

            return {
                "status": "success",
                "data": {
                    "proxy_running": proxy_running,
                    "cert_installed": manager.cert_installed,
                    "su_available": manager.su_available,
                    "device_ip": manager.device_ip,
                    "proxy_port": manager.proxy_port,
                    "proxy_host": "0.0.0.0",
                },
            }
        else:
            # Нет активного менеджера
            return {
                "status": "success",
                "data": {
                    "proxy_running": False,
                    "cert_installed": False,
                    "su_available": False,
                    "device_ip": None,
                    "proxy_port": 8081,
                    "proxy_host": "0.0.0.0",
                },
            }

    except Exception as e:
        logger.error(f"Error getting mitmproxy status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/device/{device_id}/mitmproxy/start")
async def start_mitmproxy_proxy(device_id: str):
    """Start mitmproxy proxy for a device"""
    try:
        # Проверяем, есть ли уже запущенный менеджер
        if device_id in _mitmproxy_managers:
            manager = _mitmproxy_managers[device_id]
            if manager.proxy_task and not manager.proxy_task.done():
                return {
                    "status": "success",
                    "message": "Mitmproxy is already running",
                    "data": {
                        "proxy_running": True,
                        "proxy_port": manager.proxy_port,
                        "proxy_host": "0.0.0.0",
                    },
                }
            else:
                # Очищаем старый менеджер
                await manager.stop()
                del _mitmproxy_managers[device_id]

        # Создаем новый менеджер
        mitmproxy_manager = await get_mitmproxy_manager(device_id)

        # Инициализируем менеджер
        if not await mitmproxy_manager.start():
            raise HTTPException(
                status_code=500, detail="Failed to initialize mitmproxy manager"
            )

        # Запускаем прокси
        success = await mitmproxy_manager.start_proxy()

        if success:
            # Сохраняем менеджер для дальнейшего использования
            _mitmproxy_managers[device_id] = mitmproxy_manager

            return {
                "status": "success",
                "message": "Mitmproxy started successfully",
                "data": {
                    "proxy_running": True,
                    "proxy_port": mitmproxy_manager.proxy_port,
                    "proxy_host": "0.0.0.0",
                    "proxy_setting": f"{mitmproxy_manager.backend_ip}:{mitmproxy_manager.proxy_port}",
                },
            }
        else:
            await mitmproxy_manager.stop()
            raise HTTPException(status_code=500, detail="Failed to start mitmproxy")

    except Exception as e:
        logger.error(f"Error starting mitmproxy: {str(e)}")
        # Очищаем состояние в случае ошибки
        if device_id in _mitmproxy_managers:
            try:
                await _mitmproxy_managers[device_id].stop()
            except:
                pass
            del _mitmproxy_managers[device_id]
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/device/{device_id}/mitmproxy/stop")
async def stop_mitmproxy_proxy(device_id: str):
    """Stop mitmproxy proxy for a device"""
    try:
        if device_id not in _mitmproxy_managers:
            return {
                "status": "success",
                "message": "Mitmproxy is not running",
                "data": {"proxy_running": False},
            }

        manager = _mitmproxy_managers[device_id]

        # Останавливаем прокси (stop() уже вызывает stop_proxy_threadsafe() внутри)
        success = await manager.stop()

        # Удаляем из глобального состояния
        del _mitmproxy_managers[device_id]

        return {
            "status": "success",
            "message": "Mitmproxy stopped successfully",
            "data": {"proxy_running": False},
        }

    except Exception as e:
        logger.error(f"Error stopping mitmproxy: {str(e)}")
        # Очищаем состояние в любом случае
        if device_id in _mitmproxy_managers:
            del _mitmproxy_managers[device_id]
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/device/{device_id}/mitmproxy/generate-certificate")
async def generate_mitmproxy_certificate(device_id: str):
    """Generate and return mitmproxy certificate"""
    try:
        mitmproxy_manager = await get_mitmproxy_manager(device_id)

        if not await mitmproxy_manager.start():
            raise HTTPException(
                status_code=500, detail="Failed to initialize mitmproxy manager"
            )

        cert_path = await mitmproxy_manager.generate_certificate()

        if cert_path and os.path.exists(cert_path):
            # Читаем содержимое сертификата
            with open(cert_path, "r") as f:
                cert_content = f.read()

            return {
                "status": "success",
                "message": "Certificate generated successfully",
                "data": {
                    "certificate": cert_content,
                    "cert_path": cert_path,
                    "download_url": f"/api/v1/dynamic-testing/device/{device_id}/mitmproxy/download-certificate",
                },
            }
        else:
            raise HTTPException(
                status_code=500, detail="Failed to generate certificate"
            )

    except Exception as e:
        logger.error(f"Error generating certificate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/device/{device_id}/mitmproxy/download-certificate")
async def download_mitmproxy_certificate(device_id: str):
    """Download mitmproxy certificate file"""
    try:
        from fastapi.responses import FileResponse

        certs_dir = "/tmp/mitmproxy/certs"
        cert_path = os.path.join(certs_dir, "mitmproxy-ca-cert.pem")

        if not os.path.exists(cert_path):
            # Генерируем сертификат если его нет
            mitmproxy_manager = await get_mitmproxy_manager(device_id)
            await mitmproxy_manager.start()
            cert_path = await mitmproxy_manager.generate_certificate()

            if not cert_path or not os.path.exists(cert_path):
                raise HTTPException(status_code=404, detail="Certificate not found")

        return FileResponse(
            cert_path,
            media_type="application/x-pem-file",
            filename=f"mitmproxy-ca-cert-{device_id.replace(':', '_')}.pem",
            headers={
                "Content-Disposition": f"attachment; filename=mitmproxy-ca-cert-{device_id.replace(':', '_')}.pem"
            },
        )

    except Exception as e:
        logger.error(f"Error downloading certificate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/device/{device_id}/mitmproxy/install-certificate")
async def install_mitmproxy_certificate(device_id: str):
    """Install mitmproxy certificate on device"""
    try:
        mitmproxy_manager = await get_mitmproxy_manager(device_id)

        if not await mitmproxy_manager.start():
            raise HTTPException(
                status_code=500, detail="Failed to initialize mitmproxy manager"
            )

        success = await mitmproxy_manager.install_certificate(None)

        if success:
            return {
                "status": "success",
                "message": "Certificate installed successfully on device",
                "data": {"cert_installed": True},
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to install certificate")

    except Exception as e:
        logger.error(f"Error installing certificate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/device/{device_id}/mitmproxy/configure-proxy")
async def configure_device_proxy(device_id: str):
    """Configure proxy settings on device"""
    try:
        mitmproxy_manager = await get_mitmproxy_manager(device_id)

        if not await mitmproxy_manager.start():
            raise HTTPException(
                status_code=500, detail="Failed to initialize mitmproxy manager"
            )

        success = await mitmproxy_manager.configure_device_proxy(None)

        if success:
            return {
                "status": "success",
                "message": "Proxy configured successfully on device",
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to configure proxy")

    except Exception as e:
        logger.error(f"Error configuring proxy: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/device/{device_id}/mitmproxy/export")
async def export_mitmproxy_traffic(device_id: str, format: str = "json"):
    """Export captured traffic in specified format"""
    try:
        mitmproxy_manager = await get_mitmproxy_manager(device_id)

        if not await mitmproxy_manager.start():
            raise HTTPException(
                status_code=500, detail="Failed to initialize mitmproxy manager"
            )

        exported_data = await mitmproxy_manager.export_traffic(format)

        if format == "json" or format == "har":
            from fastapi.responses import JSONResponse

            return JSONResponse(
                {"status": "success", "format": format, "data": exported_data}
            )
        else:
            from fastapi.responses import Response

            return Response(
                content=exported_data,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=traffic_{device_id}_{int(time.time())}.{format}"
                },
            )

    except Exception as e:
        logger.error(f"Error exporting traffic: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/device/{device_id}/mitmproxy/clear-traffic")
async def clear_mitmproxy_traffic(device_id: str):
    """Clear captured traffic data"""
    try:
        if device_id not in _mitmproxy_managers:
            return {
                "status": "success",
                "message": "No active mitmproxy session found - nothing to clear",
            }

        manager = _mitmproxy_managers[device_id]
        await manager.clear_traffic()

        return {"status": "success", "message": "Traffic data cleared successfully"}

    except Exception as e:
        logger.error(f"Error clearing traffic: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/device/{device_id}/mitmproxy/check-proxy")
async def check_mitmproxy_proxy(device_id: str):
    """Check if mitmproxy proxy is actually listening and accessible"""
    try:
        if device_id not in _mitmproxy_managers:
            return {
                "status": "error",
                "message": "No active mitmproxy session",
                "accessible": False,
            }

        manager = _mitmproxy_managers[device_id]

        # Проверяем статус задачи
        proxy_task_alive = (
            manager.proxy_task is not None and not manager.proxy_task.done()
        )

        # Проверяем есть ли ошибки в задаче
        proxy_error = (
            getattr(manager.proxy_task, "error", None) if manager.proxy_task else None
        )

        # Проверяем доступность порта
        import socket

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", manager.proxy_port))
            sock.close()
            port_accessible = result == 0
        except Exception as e:
            port_accessible = False
            logger.warning(f"Error checking port accessibility: {e}")

        return {
            "status": "success",
            "data": {
                "proxy_task_alive": proxy_task_alive,
                "proxy_error": str(proxy_error) if proxy_error else None,
                "port_accessible": port_accessible,
                "proxy_port": manager.proxy_port,
                "proxy_host": "0.0.0.0",
                "accessible": proxy_task_alive and port_accessible and not proxy_error,
            },
        }

    except Exception as e:
        logger.error(f"Error checking mitmproxy proxy: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/device/{device_id}/mitmproxy/logs")
async def get_mitmproxy_logs(device_id: str):
    """Get detailed logs for debugging mitmproxy issues"""
    try:
        import logging
        import io

        # Получаем логи из всех логгеров
        logs = []

        # Получаем root logger
        root_logger = logging.getLogger()

        # Создаем строковый буфер для захвата логов
        log_stream = io.StringIO()

        # Временно добавляем handler для захвата
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        root_logger.addHandler(handler)

        # Если есть активный менеджер - получаем его состояние
        debug_info = {
            "device_id": device_id,
            "manager_exists": device_id in _mitmproxy_managers,
            "timestamp": time.time(),
        }

        if device_id in _mitmproxy_managers:
            manager = _mitmproxy_managers[device_id]
            debug_info.update(
                {
                    "proxy_task_exists": manager.proxy_task is not None,
                    "proxy_task_alive": (
                        manager.proxy_task is not None and not manager.proxy_task.done()
                        if manager.proxy_task
                        else False
                    ),
                    "proxy_task_error": str(getattr(manager.proxy_task, "error", None)),
                    "device_ip": manager.device_ip,
                    "proxy_port": manager.proxy_port,
                    "su_available": manager.su_available,
                    "cert_installed": manager.cert_installed,
                }
            )

        # Убираем временный handler
        root_logger.removeHandler(handler)

        return {
            "status": "success",
            "data": {
                "debug_info": debug_info,
                "logs": log_stream.getvalue().split("\n")[-50:],  # Последние 50 строк
            },
        }

    except Exception as e:
        logger.error(f"Error getting mitmproxy logs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
