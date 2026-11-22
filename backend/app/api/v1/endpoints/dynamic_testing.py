import logging
import json
import os
import tempfile
from typing import Dict, List, Optional

import aiofiles
import aiofiles.os
from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    Depends,
)

from app.core.app_manager import AsyncStorageService
from app.modules.module_manager import ModuleManager
from app.dynamic.communication.websocket_manager import WebSocketManager
from app.dynamic.communication.vnc_proxy import VncProxy
from app.dynamic.device_management.device_manager import DeviceManager
from app.dynamic.device_management.emulator_manager import EmulatorManager
from app.dynamic.tools.android import FileManager, RemoteShell
from app.dynamic.utils.app_installer import AppInstaller
from app.dynamic.tools.aurora import AuroraTerminal
from app.dynamic.tools.aurora import AuroraFileBrowser

router = APIRouter()
websocket_manager = WebSocketManager()
logger = logging.getLogger(__name__)


def get_emulator_manager():
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
    emulators_path = os.getenv("EMULATORS_PATH", "/app/emulators")
    return EmulatorManager.get_instance(redis_url, emulators_path)


@router.get("/devices")
async def get_devices(
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
) -> List[Dict]:
    """
    Returns a list of available devices with their type and OS information.

    Device types:
    - physical: Android device connected via adb connect/adb pair
    - emulator_android: Android emulator (Docker-based)
    - emulator_aurora: Aurora OS emulator (Docker-based)
    """
    devices = []
    emulator_docker_ips = set()

    try:
        # First get running emulators to build a map of Docker IPs
        try:
            emulators = await emulator_manager.get_running_emulators()
            for emulator in emulators:
                # Track emulator container IDs to avoid duplicates from ADB
                if emulator.get("container_id"):
                    emulator_docker_ips.add(emulator.get("container_id"))

                os_type = emulator.get("os_type", "android")
                mapped_ports = emulator.get("mapped_ports", {})

                if os_type == "android":
                    adb_port = mapped_ports.get("adb", 5555)
                    udid = f"127.0.0.1:{adb_port}"
                elif os_type == "aurora":
                    ssh_port = mapped_ports.get("ssh", 2223)
                    udid = f"127.0.0.1:{ssh_port}"
                else:
                    continue

                devices.append(
                    {
                        "udid": udid,
                        "name": emulator.get("name", udid),
                        "type": f"emulator_{os_type}",
                        "os_type": os_type,
                        "status": "device",
                        "container_id": emulator.get("container_id"),
                        "mapped_ports": mapped_ports,
                    }
                )
        except Exception as e:
            logger.warning("Failed to get running emulators: %s", str(e))

        # Then get ADB devices, filtering out Docker emulators already listed
        seen_udids = {d["udid"] for d in devices}
        try:
            device_manager = DeviceManager()
            adb_devices = await device_manager.get_devices()

            for device in adb_devices:
                udid = device.get("udid", "")
                # Skip Docker IPs that are already represented via emulator entries
                if udid.startswith("172.19."):
                    continue
                # Same emulator reported by ADB as host.docker.internal:port etc.
                if DeviceManager.canonical_id(udid) in seen_udids:
                    continue

                device_type = (
                    "physical"
                    if device.get("connection") == "usb"
                    else "emulator_android"
                )
                devices.append(
                    {
                        "udid": udid,
                        "name": device.get("name", udid),
                        "type": device_type,
                        "os_type": "android",
                        "status": device.get("status", "device"),
                        "connection": device.get("connection"),
                    }
                )
        except Exception as e:
            logger.warning("Failed to get ADB devices: %s", str(e))

    except Exception as e:
        logger.error("Error getting devices: %s", str(e))

    return devices


@router.post("/device/{device_id}/start")
async def start_device_server(
    device_id: str,
    os_type: Optional[str] = Query(None, description="Device OS type"),
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """
    Starts the device server (scrcpy for Android, no-op for Aurora)
    """
    if os_type == "aurora":
        return {
            "status": "success",
            "data": {"message": "Aurora emulator uses VNC, no server needed"},
        }

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


@router.post("/device/{device_id}/stop")
async def stop_device_server(
    device_id: str,
    os_type: Optional[str] = Query(None, description="Device OS type"),
):
    """
    Stop the device server (scrcpy for Android, no-op for Aurora)
    """
    if os_type == "aurora":
        return {"status": "success"}

    device_manager = DeviceManager()
    device = await device_manager.get_device(device_id)

    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    try:
        await device.kill_server()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.websocket("/ws/{device_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    device_id: str,
    action: Optional[str] = Query(None),
    os_type: Optional[str] = Query(None),
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """
    Main WebSocket endpoint for interacting with the device.

    Query params:
    - action: 'stream', 'shell', 'file_manager', or module name
    - os_type: 'android' or 'aurora' (for tool selection)
    """
    # device_id is the device's identity (what the frontend sees) and is never
    # rewritten. The container-reachable address is only used where a real
    # connection is made (module proxy, adb shell, file manager).
    device_id = DeviceManager.canonical_id(device_id)
    adb_address = DeviceManager.get_adb_address(device_id)
    logger.info(
        "WebSocket endpoint: device_id=%s, os_type=%s, action=%s",
        device_id,
        os_type,
        action,
    )

    module_manager = ModuleManager.get_instance()
    if action in module_manager.module_name_mappings:
        module_name = module_manager.module_name_mappings[action]

        exists = await module_manager.check_module_exists(module_name)

        if not exists:
            await websocket.close(code=4004, reason="Module not found")
            return

        query_params = dict(websocket.query_params)
        logger.info("Proxying to module %s with device_id %s", module_name, adb_address)
        await module_manager.proxy_websocket(
            websocket=websocket,
            module_name=module_name,
            device_id=adb_address,
            query_params=query_params,
        )
        return

    try:
        device_exists = False
        emulator_name = None
        emulator_subpath = None

        if os_type == "aurora":
            emulators = await emulator_manager.get_running_emulators()
            for emulator in emulators:
                if emulator.get("os_type") == "aurora":
                    ssh_port = emulator.get("mapped_ports", {}).get("ssh", 2223)
                    udid = f"127.0.0.1:{ssh_port}"
                    if udid == device_id:
                        device_exists = True
                        emulator_name = emulator.get("name")
                        config = emulator.get("config", {})
                        volumes = config.get("volumes", [])
                        if volumes:
                            emulator_subpath = volumes[0].get("subpath")
                        break
        else:
            device_manager = DeviceManager()
            device = await device_manager.get_device(device_id)
            device_exists = device is not None

        if not device_exists:
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
            logger.info(
                "Starting shell session for device %s (os_type: %s)", device_id, os_type
            )

            if os_type == "aurora":

                host, port = DeviceManager.get_connect_endpoint(
                    device_id, default_port=2223
                )
                shell = AuroraTerminal(
                    websocket, device_id, host, port, emulator_subpath=emulator_subpath
                )
            else:
                shell = RemoteShell(websocket, adb_address)

            if not await shell.start():
                logger.error("Failed to start shell for device %s", device_id)
                await websocket.close(code=4000, reason="Failed to start shell")
                return

            logger.info(
                "Shell started successfully for device %s, waiting for messages...",
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
                            if "bytes" in message:
                                logger.info(
                                    "Received bytes message: %s bytes",
                                    len(message["bytes"]),
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
            logger.info(
                "Starting file manager session for device %s (os_type: %s)",
                device_id,
                os_type,
            )

            if os_type == "aurora":
                host, port = DeviceManager.get_connect_endpoint(
                    device_id, default_port=2223
                )
                file_manager = AuroraFileBrowser(
                    websocket, device_id, host, port, emulator_subpath=emulator_subpath
                )
                default_path = "/home/defaultuser"
            else:
                file_manager = FileManager(websocket, adb_address)
                default_path = "/data/local/tmp"

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
                                msg_data = json.loads(message["text"])
                                await file_manager.handle_message(msg_data)
                            elif "bytes" in message:
                                logger.info(
                                    "Received bytes message: %s bytes",
                                    len(message["bytes"]),
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

        elif action == "vnc":
            logger.info(
                "Starting VNC proxy session for device %s (os_type: %s)",
                device_id,
                os_type,
            )

            if os_type != "aurora":
                logger.error("VNC action only supported for Aurora OS devices")
                await websocket.close(
                    code=4000, reason="VNC only supported for Aurora OS"
                )
                return

            try:
                emulators = await emulator_manager.get_running_emulators()
                vnc_port = None
                emulator_name = None

                for emulator in emulators:
                    if emulator.get("os_type") == "aurora":
                        ssh_port = emulator.get("mapped_ports", {}).get("ssh", 2223)
                        udid = f"127.0.0.1:{ssh_port}"
                        if udid == device_id:
                            config = emulator.get("config", {})
                            ports = config.get("ports", {})
                            vnc_port = ports.get("websocket", 5701)
                            emulator_name = emulator.get("name")
                            break

                if vnc_port is None or emulator_name is None:
                    logger.error(
                        "Could not determine VNC WebSocket port for device %s",
                        device_id,
                    )
                    await websocket.close(
                        code=4000, reason="VNC WebSocket port not found"
                    )
                    return

                container_hostname = f"emulator_{emulator_name}"
                vnc_url = f"ws://{container_hostname}:{vnc_port}"
                logger.info(
                    "Creating VNC proxy for device %s to %s", device_id, vnc_url
                )

                vnc_proxy = await VncProxy.create_proxy(websocket, device_id, vnc_url)

                logger.info(
                    "VNC proxy established for device %s, waiting for messages...",
                    device_id,
                )

                try:
                    while True:
                        try:
                            message = await websocket.receive()

                            if message["type"] == "websocket.disconnect":
                                logger.info("VNC WebSocket disconnect received")
                                break
                            if message["type"] == "websocket.receive":
                                if "bytes" in message:
                                    await vnc_proxy.handle_client_message(
                                        message["bytes"]
                                    )
                                elif "text" in message:
                                    # VNC is binary, but handle text as fallback
                                    await vnc_proxy.handle_client_message(
                                        message["text"].encode()
                                    )
                            else:
                                logger.info("Unknown message type: %s", message["type"])
                        except Exception as e:
                            logger.error("Error processing VNC message: %s", str(e))
                            break
                except WebSocketDisconnect:
                    logger.info("VNC WebSocket disconnected for device %s", device_id)
                except Exception as e:
                    logger.error("Error in VNC session: %s", str(e))
                finally:
                    await vnc_proxy.close()

            except Exception as e:
                logger.error("Failed to establish VNC proxy: %s", str(e))
                try:
                    await websocket.close(
                        code=4000, reason=f"VNC proxy error: {str(e)}"
                    )
                except Exception:
                    pass

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

        await websocket_manager.handle_multiplex_without_device(websocket)

    except WebSocketDisconnect:
        logger.info("Multiplex WebSocket connection closed")
    except Exception as e:
        logger.error("Error in multiplex endpoint: %s", str(e))
        try:
            await websocket.close(code=4000, reason=str(e))
        except Exception:
            pass


@router.post("/device/{device_id}/install-app")
async def install_app_on_device(
    device_id: str,
    request: dict,
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """
    Install an APK or RPM file on the specified device
    """
    try:
        file_hash = request.get("file_hash")
        app_name = request.get("app_name")
        os_type = request.get("os_type", "android")

        if not file_hash or not app_name:
            raise HTTPException(
                status_code=400, detail="file_hash and app_name are required"
            )

        storage = AsyncStorageService()

        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise HTTPException(status_code=404, detail="File not found in storage")

        file_type = file_info.get("file_type")

        # Validate file type matches OS type
        if os_type == "android" and file_type != "apk":
            raise HTTPException(
                status_code=400, detail="Android devices require APK files"
            )
        elif os_type == "aurora" and file_type != "rpm":
            raise HTTPException(
                status_code=400, detail="Aurora OS devices require RPM files"
            )

        storage_dir = "/shared_data"
        folder_path = file_info.get("folder_path")
        original_name = file_info.get("original_name")

        app_path = f"{storage_dir}/{folder_path}/{original_name}"

        if not await aiofiles.os.path.exists(app_path):
            raise HTTPException(
                status_code=404, detail=f"App file not found at: {app_path}"
            )

        emulator_subpath = None
        if os_type == "aurora":
            emulators = await emulator_manager.get_running_emulators()
            for emulator in emulators:
                if emulator.get("os_type") == "aurora":
                    ssh_port = emulator.get("mapped_ports", {}).get("ssh", 2223)
                    udid = f"127.0.0.1:{ssh_port}"
                    if udid == device_id:
                        config = emulator.get("config", {})
                        volumes = config.get("volumes", [])
                        if volumes:
                            emulator_subpath = volumes[0].get("subpath")
                        break

        if file_type == "apk":
            success, message = await AppInstaller.install_apk(
                DeviceManager.get_adb_address(device_id), app_path
            )
        elif file_type == "rpm":
            success, message = await AppInstaller.install_rpm(
                device_id, app_path, emulator_subpath=emulator_subpath
            )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported file type: {file_type}"
            )

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
        raise HTTPException(
            status_code=500, detail=f"Error installing app: {str(e)}"
        ) from e


@router.post("/device/{device_id}/install-apk-direct")
async def install_apk_direct(
    device_id: str,
    apk_file: UploadFile = File(...),
    os_type: Optional[str] = Query(
        "android", description="Device OS type: android or aurora"
    ),
    emulator_manager: EmulatorManager = Depends(get_emulator_manager),
):
    """
    Install an APK or RPM file directly on the device without storing in database
    """
    try:
        file_ext = apk_file.filename.lower().split(".")[-1]

        # Validate file type based on OS
        if os_type == "android" and file_ext != "apk":
            raise HTTPException(
                status_code=400, detail="Android devices require APK files"
            )
        elif os_type == "aurora" and file_ext != "rpm":
            raise HTTPException(
                status_code=400, detail="Aurora OS devices require RPM files"
            )
        elif file_ext not in ["apk", "rpm"]:
            raise HTTPException(
                status_code=400, detail="Only APK and RPM files are supported"
            )

        fd, temp_file_path = tempfile.mkstemp(suffix=f".{file_ext}")
        os.close(fd)
        content = await apk_file.read()
        async with aiofiles.open(temp_file_path, "wb") as temp_file:
            await temp_file.write(content)

        try:
            logger.info(
                "Installing %s %s on device %s",
                file_ext.upper(),
                apk_file.filename,
                device_id,
            )

            emulator_subpath = None
            if os_type == "aurora":
                emulators = await emulator_manager.get_running_emulators()
                for emulator in emulators:
                    if emulator.get("os_type") == "aurora":
                        ssh_port = emulator.get("mapped_ports", {}).get("ssh", 2223)
                        udid = f"127.0.0.1:{ssh_port}"
                        if udid == device_id:
                            config = emulator.get("config", {})
                            volumes = config.get("volumes", [])
                            if volumes:
                                emulator_subpath = volumes[0].get("subpath")
                            break

            if file_ext == "apk":
                success, message = await AppInstaller.install_apk(
                    DeviceManager.get_adb_address(device_id), temp_file_path
                )
            else:  # rpm
                success, message = await AppInstaller.install_rpm(
                    device_id, temp_file_path, emulator_subpath=emulator_subpath
                )

            if success:
                logger.info(
                    "Successfully installed %s on device %s",
                    apk_file.filename,
                    device_id,
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
                await aiofiles.os.remove(temp_file_path)
            except Exception as e:
                logger.warning(
                    "Failed to cleanup temporary file %s: %s", temp_file_path, str(e)
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error installing file directly: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error installing file: {str(e)}"
        ) from e


# Physical Device Management Endpoints


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


@router.post("/device/pair-wifi")
async def pair_wifi_device(request: dict):
    """Pair with a device via WiFi (Android 11+ wireless debugging)"""
    try:
        ip_address = request.get("ip_address")
        port = request.get("port")
        pairing_port = request.get("pairing_port")
        pairing_code = request.get("pairing_code")

        if not ip_address:
            raise HTTPException(status_code=400, detail="ip_address is required")
        if not port:
            raise HTTPException(status_code=400, detail="port is required")
        if not pairing_port:
            raise HTTPException(status_code=400, detail="pairing_port is required")
        if not pairing_code:
            raise HTTPException(status_code=400, detail="pairing_code is required")

        device_manager = DeviceManager()
        success = await device_manager.pair_wifi_device(
            ip_address, port, pairing_port, pairing_code
        )

        if success:
            return {
                "status": "success",
                "message": f"Successfully paired with device at {ip_address}:{port}",
                "data": {"ip_address": ip_address, "port": port, "paired": True},
            }

        raise HTTPException(
            status_code=500,
            detail=f"Failed to pair with device at {ip_address}:{port}",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error pairing WiFi device: %s", str(e))
        raise HTTPException(
            status_code=500, detail=f"Error pairing WiFi device: {str(e)}"
        ) from e
