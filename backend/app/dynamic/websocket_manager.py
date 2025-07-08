from typing import Dict, Set
from fastapi import WebSocket
import json
import logging
from .websocket_proxy import WebSocketProxy

class WebSocketManager:
    """
    WebSocket connection management:
    - Storing active connections
    - Routing messages between client and device
    - Handling different message types (management, video, audio)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WebSocketManager, cls).__new__(cls)
            cls._instance.active_connections = {}
            cls._instance.proxies = {}
            cls._instance.logger = logging.getLogger(__name__)
        return cls._instance

    async def connect(self, websocket: WebSocket, device_id: str):
        """
        Establishes a WebSocket connection with the device
        """
        try:
            self.logger.info(f"Connecting WebSocket for device '{device_id}' (len: {len(device_id)})")
            
            if device_id not in self.active_connections:
                self.active_connections[device_id] = set()
                self.proxies[device_id] = {}
                self.logger.info(f"Created new connection pool for device '{device_id}'")
                
            self.active_connections[device_id].add(websocket)
            
            if self.proxies[device_id]:
                self.logger.info(f"Closing existing proxies for device '{device_id}' (count: {len(self.proxies[device_id])})")
                for existing_ws, existing_proxy in list(self.proxies[device_id].items()):
                    await existing_proxy.close()
                    try:
                        await existing_ws.close()
                    except:
                        pass
                self.proxies[device_id].clear()
                self.active_connections[device_id].clear()
                self.active_connections[device_id].add(websocket)
                
            try:
                self.logger.info(f"Creating WebSocket proxy for device '{device_id}' on port 8886")
                proxy = await WebSocketProxy.create_proxy(websocket, device_id, 8886)
                self.proxies[device_id][websocket] = proxy
                self.logger.info(f"WebSocket proxy initialized for device '{device_id}' (local:{proxy.local_port} -> remote:{proxy.remote_port})")
            except Exception as e:
                self.logger.error(f"Failed to create WebSocket proxy for device '{device_id}': {str(e)}")
                await self.disconnect(websocket, device_id)
                raise
                
        except Exception as e:
            self.logger.error(f"Error in WebSocket connection: {str(e)}")
            try:
                await websocket.close(code=4000, reason=str(e))
            except Exception:
                pass
            raise

    async def disconnect(self, websocket: WebSocket, device_id: str):
        """
        Closes the WebSocket connection with the device
        """
        if device_id in self.active_connections:
            self.active_connections[device_id].discard(websocket)
            
            if device_id in self.proxies and websocket in self.proxies[device_id]:
                proxy = self.proxies[device_id].pop(websocket)
                await proxy.close()
            
            if not self.active_connections[device_id]:
                del self.active_connections[device_id]
                if device_id in self.proxies:
                    del self.proxies[device_id]
        
        self.logger.info(f"WebSocket connection closed for device {device_id}")

    async def broadcast_to_device(self, device_id: str, message: str):
        """Sends a message to all connected clients of the device"""
        if device_id not in self.active_connections:
            return
        
        for connection in list(self.active_connections[device_id]):
            try:
                await connection.send_text(message)
            except Exception as e:
                self.logger.error(f"Error sending message to websocket: {e}")
                await self.disconnect(connection, device_id)

    async def handle_websocket_message(self, websocket: WebSocket, device_id: str, message: str):
        """
        Handles messages from the WebSocket client
        """
        self.logger.info(f"Handling message for device '{device_id}', available devices: {list(self.proxies.keys())}")
        if device_id in self.proxies and websocket in self.proxies[device_id]:
            proxy = self.proxies[device_id][websocket]
            await proxy.handle_client_message(message)
        else:
            self.logger.error(f"No proxy found for device '{device_id}' (empty: {device_id == ''})")

    async def handle_binary_message(self, websocket: WebSocket, device_id: str, data: bytes):
        """
        Handles binary messages from the WebSocket client
        """
        self.logger.info(f"Handling binary message for device '{device_id}', available devices: {list(self.proxies.keys())}")
        if device_id in self.proxies and websocket in self.proxies[device_id]:
            proxy = self.proxies[device_id][websocket]
            await proxy.handle_client_binary(data)
        else:
            self.logger.error(f"No proxy found for device '{device_id}' (empty: {device_id == ''})")

    async def handle_multiplex(self, websocket: WebSocket, device_id: str):
        """
        Handles multiplexed WebSocket connection for a specific device
        """
        try:
            if device_id not in self.active_connections:
                self.active_connections[device_id] = set()
                self.proxies[device_id] = {}
                
            self.active_connections[device_id].add(websocket)
            
            try:
                proxy = await WebSocketProxy.create_proxy(websocket, device_id, 8886)
                self.proxies[device_id][websocket] = proxy
                self.logger.info(f"WebSocket proxy initialized for multiplex connection (device: {device_id}, local:{proxy.local_port} -> remote:8886)")
            except Exception as e:
                self.logger.error(f"Failed to create WebSocket proxy for multiplex connection: {str(e)}")
                await self.disconnect(websocket, device_id)
                raise
            
            while True:
                try:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        self.logger.info(f"Multiplex connection closed for device {device_id}")
                        break
                    elif message["type"] == "websocket.receive":
                        if "bytes" in message:
                            data = message["bytes"]
                            await proxy.handle_client_binary(data)
                        elif "text" in message:
                            try:
                                data = json.loads(message["text"])
                                await proxy.handle_client_message(message["text"])
                            except json.JSONDecodeError:
                                self.logger.error("Invalid JSON in text message")
                except Exception as e:
                    self.logger.error(f"Error handling multiplex message: {str(e)}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error in multiplex handler: {str(e)}")
            try:
                await websocket.close(code=4000, reason=str(e))
            except Exception:
                pass
        finally:
            await self.disconnect(websocket, device_id)

    async def handle_multiplex_simple(self, websocket: WebSocket):
        """
        Handles a simple multiplexed WebSocket connection without device_id
        """
        try:
            self.logger.info("Handling simple multiplex connection")
            
            while True:
                try:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        self.logger.info("Simple multiplex connection closed")
                        break
                    elif message["type"] == "websocket.receive":
                        if "text" in message:
                            try:
                                data = json.loads(message["text"])
                                self.logger.info(f"Received multiplex message: {data}")
                                if data.get("type") == "ping":
                                    await websocket.send_text(json.dumps({
                                        "type": "pong", 
                                        "timestamp": data.get("timestamp", 0)
                                    }))
                            except json.JSONDecodeError:
                                self.logger.error("Invalid JSON in text message")
                        elif "bytes" in message:
                            self.logger.info(f"Received binary message: {len(message['bytes'])} bytes")
                except Exception as e:
                    self.logger.error(f"Error handling simple multiplex message: {str(e)}")
                    break
                    
        except Exception as e:
            self.logger.error(f"Error in simple multiplex handler: {str(e)}")
            try:
                await websocket.close(code=4000, reason=str(e))
            except Exception:
                pass
