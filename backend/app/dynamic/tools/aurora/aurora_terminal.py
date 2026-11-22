import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import WebSocket

from app.dynamic.communication.base_websocket_manager import BaseWebSocketManager
from app.dynamic.tools.aurora.aurora_ssh_client import AuroraSSHClient

logger = logging.getLogger(__name__)


class AuroraTerminal(BaseWebSocketManager):
    """Terminal for Aurora OS emulators"""

    def __init__(
        self,
        websocket: WebSocket,
        device_id: str,
        host: str,
        port: int,
        emulator_subpath: Optional[str] = None,
    ):
        super().__init__(websocket, "aurora_terminal")
        self.device_id = device_id
        self.host = host
        self.port = port
        self.ssh_client = AuroraSSHClient(host, port, emulator_subpath=emulator_subpath)
        self.is_running = False
        self.process: Optional[asyncio.subprocess.Process] = None
        self._read_task = None
        self._error_task = None
        self.rows = 30
        self.cols = 100

    async def start(self):
        """Start terminal session"""
        if self.is_running:
            return True

        try:
            # Check SSH connectivity first
            if not await self.ssh_client.check_connectivity():
                await self.send_response(
                    {
                        "type": "error",
                        "message": "Failed to connect to Aurora OS device",
                    }
                )
                return False

            # Build SSH command for interactive shell with PTY allocation
            ssh_cmd = self.ssh_client._get_ssh_base_command() + ["-tt"]

            logger.info(
                "Starting interactive SSH shell for Aurora device %s", self.device_id
            )

            self.process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "TERM": "xterm-256color"},
            )

            if not self.process:
                logger.error("Failed to create SSH process")
                return False

            self.is_running = True

            # Start reading output
            self._read_task = asyncio.create_task(self._read_from_process())

            return True

        except Exception as e:
            logger.error("Error starting Aurora terminal: %s", e)
            await self.send_response(
                {
                    "type": "error",
                    "message": f"Failed to start terminal: {str(e)}",
                }
            )
            await self.stop()
            return False

    async def handle_input(self, data: str):
        """Handle incoming data from WebSocket"""
        try:
            try:
                message = json.loads(data)
                if isinstance(message, dict):
                    msg_type = message.get("type")

                    if msg_type == "resize":
                        self.rows = message.get("rows", 30)
                        self.cols = message.get("cols", 100)
                        logger.info(
                            "Aurora terminal resized to: %sx%s", self.rows, self.cols
                        )
                        return

                    if msg_type == "input":
                        input_data = message.get("input", "")
                        if self.is_running and self.process and self.process.stdin:
                            self.process.stdin.write(input_data.encode())
                            await self.process.stdin.drain()
                        return

            except json.JSONDecodeError:
                pass

            # Treat as raw input
            if self.is_running and self.process and self.process.stdin:
                logger.info("Writing raw input to process stdin: %r", data)
                self.process.stdin.write(data.encode())
                await self.process.stdin.drain()
                logger.info("Data written and drained")
            else:
                logger.error(
                    "Cannot write input: is_running=%s, process=%s, stdin=%s",
                    self.is_running,
                    self.process,
                    self.process.stdin if self.process else None,
                )

        except Exception as e:
            logger.error("Error handling input: %s", e, exc_info=True)

    async def _read_from_process(self):
        """Read output from process stdout and send to WebSocket"""
        try:
            while self.is_running and self.process and self.process.stdout:
                try:
                    data = await self.process.stdout.read(1024)

                    if not data:
                        break

                    if self.websocket.client_state.CONNECTED:
                        await self.websocket.send_bytes(data)

                except Exception as e:
                    logger.error("Error reading from process: %s", e)
                    break

        except asyncio.CancelledError:
            logger.info("Output reader cancelled")
        except Exception as e:
            logger.error("Error in output reader: %s", e)

        await self.stop()
        logger.info("Aurora terminal stopped")

    async def stop(self):
        """Stop terminal session"""
        self.is_running = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._error_task:
            self._error_task.cancel()
            try:
                await self._error_task
            except asyncio.CancelledError:
                pass

        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.kill()
                await self.process.wait()
            except Exception as e:
                logger.error("Error stopping process: %s", e)
            self.process = None

        logger.info("Aurora terminal stopped")

    async def resize(self, rows: int, cols: int):
        """Resize terminal"""
        self.rows = rows
        self.cols = cols
        logger.info("Terminal resized to %dx%d", rows, cols)
