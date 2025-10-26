"""
Communication module for MobSec.

This module contains classes and utilities for WebSocket communication
and proxying connections to devices.
"""

from .websocket_manager import WebSocketManager
from .websocket_proxy import WebSocketProxy
from .base_websocket_manager import BaseWebSocketManager

__all__ = ["WebSocketManager", "WebSocketProxy", "BaseWebSocketManager"]
