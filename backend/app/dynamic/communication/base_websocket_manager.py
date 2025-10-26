import json
import logging
from typing import Dict, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class BaseWebSocketManager:
    """Base class for managers working with WebSocket"""

    def __init__(self, websocket: WebSocket, manager_type: str):
        self.websocket = websocket
        self.manager_type = manager_type

    async def send_response(self, data: Dict[str, Any]):
        """Universal response sending via WebSocket"""
        try:
            if self.websocket.client_state.CONNECTED:
                await self.websocket.send_text(json.dumps(data))
            else:
                logger.warning("WebSocket not connected, cannot send response")
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")

    async def send_error(self, message: str, error_type: str = "error"):
        """Universal error sending"""
        await self.send_response(
            {"type": self.manager_type, "action": error_type, "message": message}
        )
