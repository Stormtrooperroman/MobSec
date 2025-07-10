from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from typing import List, Dict, Optional
from app.dynamic.device_manager import DeviceManager
from app.dynamic.websocket_manager import WebSocketManager
from app.dynamic.remote_shell import RemoteShell
from app.dynamic.file_manager import FileManager
import logging

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
    websocket: WebSocket,
    device_id: str,
    action: Optional[str] = Query(None)
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
        logger.info(f"WebSocket connection accepted for device '{device_id}' (len: {len(device_id)}) with action {action}")
        
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
                            await websocket_manager.handle_binary_message(websocket, device_id, message["bytes"])
                        elif "text" in message:
                            await websocket_manager.handle_websocket_message(websocket, device_id, message["text"])
                except Exception as e:
                    logger.error(f"Error handling message for device {device_id}: {str(e)}")
                    break
                    
        elif action == "shell":
            logger.info(f"Starting shell session for device {device_id}")
            shell = RemoteShell(websocket, device_id)
            if not await shell.start():
                logger.error(f"Failed to start shell for device {device_id}")
                await websocket.close(code=4000, reason="Failed to start shell")
                return
            
            logger.info(f"Shell started successfully for device {device_id}, waiting for messages...")
            
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
                                logger.info(f"Received bytes message: {len(message['bytes'])} bytes")
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
            
            logger.info(f"File manager started successfully for device {device_id}, waiting for messages...")
            
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
                                logger.info(f"Received bytes message: {len(message['bytes'])} bytes")
                                pass
                        else:
                            logger.info(f"Unknown message type: {message['type']}")
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {str(e)}")
                        break
            except WebSocketDisconnect:
                logger.info(f"File manager WebSocket disconnected for device {device_id}")
            except Exception as e:
                logger.error(f"Error in file manager session: {str(e)}")
            finally:
                await file_manager.stop()
                    
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
async def multiplex_endpoint(
    websocket: WebSocket,
    action: Optional[str] = Query(None)
):
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

