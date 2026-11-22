import asyncio
import json
import logging
from typing import Optional, Dict, Any, List

from fastapi import WebSocket

from app.dynamic.communication.base_websocket_manager import BaseWebSocketManager
from app.dynamic.tools.aurora.aurora_ssh_client import AuroraSSHClient

logger = logging.getLogger(__name__)


class AuroraFileBrowser(BaseWebSocketManager):
    """File browser for Aurora OS emulators"""

    def __init__(
        self,
        websocket: WebSocket,
        device_id: str,
        host: str,
        port: int,
        emulator_subpath: Optional[str] = None,
    ):
        super().__init__(websocket, "aurora_file_browser")
        self.device_id = device_id
        self.host = host
        self.port = port
        self.ssh_client = AuroraSSHClient(
            host, port, user="defaultuser", emulator_subpath=emulator_subpath
        )
        self.is_running = False
        self.current_path = "/home/defaultuser"
        self.current_user = "defaultuser"
        self.use_root = False
        self.su_available = False

    async def start(self):
        """Start file browser session"""
        if self.is_running:
            return True

        try:
            self.is_running = True

            if not await self.ssh_client.check_connectivity():
                await self.send_response(
                    {
                        "type": "error",
                        "message": "Failed to connect to Aurora OS device",
                    }
                )
                self.is_running = False
                return False

            result = await self.ssh_client.execute_command("whoami")
            if result["returncode"] == 0:
                self.current_user = result["stdout"].strip()

            self.su_available = True

            logger.info(
                "File browser started: user=%s, su_available=%s",
                self.current_user,
                self.su_available,
            )

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "ready",
                    "current_path": self.current_path,
                    "current_user": self.current_user,
                    "su_available": self.su_available,
                    "use_su": False,
                }
            )

            return True

        except Exception as e:
            logger.error("Error starting Aurora file browser: %s", e)
            await self.send_response(
                {
                    "type": "error",
                    "message": f"Failed to start file browser: {str(e)}",
                }
            )
            self.is_running = False
            return False

    async def list_directory(self, path: str):
        """List directory contents"""
        try:
            entries = await self.ssh_client.list_directory(path)
            self.current_path = path

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "list",
                    "path": path,
                    "entries": entries,
                }
            )
        except Exception as e:
            is_permission_denied = "Permission denied" in str(e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Failed to list directory: {str(e)}",
                    "permission_denied": is_permission_denied,
                    "path": self.current_path,
                }
            )

    async def read_file(self, path: str):
        """Read file contents"""
        try:
            content = await self.ssh_client.read_file(path)

            if content is not None:
                await self.send_response(
                    {
                        "type": "file_content",
                        "path": path,
                        "content": content,
                    }
                )
            else:
                await self.send_response(
                    {
                        "type": "error",
                        "message": f"Failed to read file: {path}",
                    }
                )
        except Exception as e:
            logger.error("Error reading file: %s", e)
            await self.send_response(
                {
                    "type": "error",
                    "message": f"Failed to read file: {str(e)}",
                }
            )

    async def write_file(self, path: str, content: str):
        """Write content to file"""
        try:
            success = await self.ssh_client.write_file(path, content)

            await self.send_response(
                {
                    "type": "file_write_result",
                    "path": path,
                    "success": success,
                }
            )
        except Exception as e:
            logger.error("Error writing file: %s", e)
            await self.send_response(
                {
                    "type": "error",
                    "message": f"Failed to write file: {str(e)}",
                }
            )

    async def delete_file(self, path: str):
        """Delete file or directory"""
        try:
            cmd = f"rm -rf {path}"
            result = await self.ssh_client.execute_command(cmd)

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "delete",
                    "path": path,
                    "success": result["returncode"] == 0,
                }
            )
        except Exception as e:
            logger.error("Error deleting file: %s", e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Failed to delete file: {str(e)}",
                }
            )

    async def download_file(self, path: str):
        """Download file from device"""
        try:
            import base64

            content = await self.ssh_client.read_file(path)

            if content is not None:
                # Encode to base64 for transfer
                content_b64 = base64.b64encode(content.encode()).decode()
                filename = path.split("/")[-1]

                await self.send_response(
                    {
                        "type": "file_manager",
                        "action": "download",
                        "filename": filename,
                        "data": content_b64,
                    }
                )
            else:
                await self.send_response(
                    {
                        "type": "file_manager",
                        "action": "error",
                        "message": f"Failed to read file: {path}",
                    }
                )
        except Exception as e:
            logger.error("Error downloading file: %s", e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Failed to download file: {str(e)}",
                }
            )

    async def upload_file(self, path: str, data: str):
        """Upload file to device"""
        try:
            import base64

            # Decode from base64
            content = base64.b64decode(data).decode()

            success = await self.ssh_client.write_file(path, content)

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "upload",
                    "path": path,
                    "success": success,
                }
            )
        except Exception as e:
            logger.error("Error uploading file: %s", e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Failed to upload file: {str(e)}",
                }
            )

    async def create_directory(self, path: str):
        """Create directory"""
        try:
            cmd = f"mkdir -p {path}"
            result = await self.ssh_client.execute_command(cmd)

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "mkdir",
                    "path": path,
                    "success": result["returncode"] == 0,
                }
            )
        except Exception as e:
            logger.error("Error creating directory: %s", e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Failed to create directory: {str(e)}",
                }
            )

    async def stop(self):
        """Stop file browser session"""
        if not self.is_running:
            return

        self.is_running = False
        logger.info("Aurora file browser stopped")

    async def _toggle_su(self):
        """Toggle between defaultuser and root by reconnecting"""
        if not self.su_available:
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": "Root access not available",
                }
            )
            return

        try:
            # Toggle user
            new_user = "root" if not self.use_root else "defaultuser"

            # Reconnect with new user
            self.ssh_client.set_user(new_user)

            # Verify connectivity with new user
            if not await self.ssh_client.check_connectivity():
                # Revert on failure
                self.ssh_client.set_user(self.current_user)
                await self.send_response(
                    {
                        "type": "file_manager",
                        "action": "error",
                        "message": f"Failed to connect as {new_user}",
                    }
                )
                return

            # Update state
            self.use_root = not self.use_root
            self.current_user = new_user

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "su_toggled",
                    "use_su": self.use_root,
                    "su_available": self.su_available,
                    "current_user": self.current_user,
                    "current_path": self.current_path,
                }
            )
        except Exception as e:
            logger.error("Error toggling su: %s", e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Failed to toggle user: {str(e)}",
                }
            )

    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming WebSocket messages"""
        try:
            msg_type = message.get("type")
            action = message.get("action")

            if msg_type == "file_manager" or action:
                action = action or msg_type

                if action == "list":
                    path = message.get("path", self.current_path)
                    await self.list_directory(path)
                elif action == "download":
                    path = message.get("path")
                    if path:
                        await self.download_file(path)
                elif action == "upload":
                    path = message.get("path")
                    data = message.get("data")
                    if path and data:
                        await self.upload_file(path, data)
                elif action == "delete":
                    path = message.get("path")
                    if path:
                        await self.delete_file(path)
                elif action == "mkdir":
                    path = message.get("path")
                    if path:
                        await self.create_directory(path)
                elif action == "toggle_su":
                    await self._toggle_su()
                else:
                    await self.send_response(
                        {
                            "type": "file_manager",
                            "action": "error",
                            "message": f"Unknown action: {action}",
                        }
                    )
        except Exception as e:
            logger.error("Error handling message: %s", e)
            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "error",
                    "message": f"Error processing message: {str(e)}",
                }
            )
