import asyncio
import logging
from typing import Optional, Dict
from fastapi import WebSocket
import aiohttp
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class WebSocketProxy:
    """
    Class for proxying WebSocket connections through ADB.
    Provides bidirectional data transfer between the client and the scrcpy server on the device.
    """

    def __init__(self, client_ws: WebSocket):
        self.client_ws = client_ws
        self.device_ws = None
        self.local_port = None
        self.remote_port = None
        self.device_id = None
        self.logger = logging.getLogger(__name__)
        self._session = None

    @classmethod
    async def create_proxy(
        cls, client_ws: WebSocket, device_id: str, remote_port: int
    ) -> "WebSocketProxy":
        """
        Creates a new proxy for a WebSocket connection
        """
        proxy = cls(client_ws)
        await proxy.init(device_id, remote_port)
        return proxy

    async def init(self, device_id: str, remote_port: int):
        """
        Initializes the proxy, establishing a connection with the device
        """
        self._session = aiohttp.ClientSession()
        self.device_id = device_id
        self.logger.info(
            f"Initializing WebSocket proxy for device '{device_id}' (len: {len(device_id)}) on port {remote_port}"
        )
        try:
            self.remote_port = remote_port
            self.local_port = remote_port

            remove_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                device_id,
                "forward",
                "--remove",
                f"tcp:{self.local_port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await remove_process.communicate()

            forward_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                device_id,
                "forward",
                f"tcp:{self.local_port}",
                f"tcp:{self.remote_port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await forward_process.communicate()

            if forward_process.returncode != 0:
                raise Exception(f"Failed to setup port forwarding: {stderr.decode()}")

            max_retries = 5
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    ws_url = f"ws://127.0.0.1:{self.local_port}/"
                    self.logger.info(
                        f"Attempting WebSocket connection to {ws_url} (attempt {attempt + 1})"
                    )

                    self.device_ws = await self._session.ws_connect(
                        ws_url, timeout=10, heartbeat=30
                    )

                    self.logger.info(
                        f"WebSocket connection established for device {device_id} (local:{self.local_port} -> remote:{self.remote_port})"
                    )

                    self._start_device_message_handler()
                    return

                except Exception as e:
                    self.logger.warning(
                        f"Connection attempt {attempt + 1} failed: {str(e)}"
                    )
                    if (
                        "Connection refused" in str(e)
                        or "cannot connect" in str(e).lower()
                    ):
                        self.logger.info(
                            "scrcpy server may not be ready yet, waiting..."
                        )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        raise

        except Exception as e:
            await self.cleanup()
            self.logger.error(f"Failed to initialize WebSocket proxy: {str(e)}")
            raise

    async def handle_client_message(self, message: str):
        """
        Handles a text message from the client
        """
        if self.device_ws and not self.device_ws.closed:
            try:
                self.logger.info(f"Sending text to device {self.device_id}: {message}")
                await self.device_ws.send_str(message)
            except Exception as e:
                self.logger.error(f"Error sending message to device: {str(e)}")
                await self.cleanup()

    async def handle_client_binary(self, data: bytes):
        """
        Handles a binary message from the client
        """
        if self.device_ws and not self.device_ws.closed:
            try:
                await self.device_ws.send_bytes(data)
            except Exception as e:
                self.logger.error(f"Error sending binary data to device: {str(e)}")
                await self.cleanup()

    def _start_device_message_handler(self):
        """
        Starts the device message handler
        """

        async def handler():
            try:
                async for msg in self.device_ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        await self.client_ws.send_text(msg.data)
                    elif msg.type == aiohttp.WSMsgType.BINARY:
                        data_preview = (
                            msg.data[:20] if len(msg.data) >= 20 else msg.data
                        )
                        await self.client_ws.send_bytes(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        self.logger.error(f"WebSocket error: {str(msg.data)}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        self.logger.info("Device WebSocket closed")
                        break
            except Exception as e:
                self.logger.error(f"Error handling device messages: {str(e)}")
            finally:
                await self.cleanup()

        asyncio.create_task(handler())

    async def cleanup(self):
        """
        Cleans up all resources, including ADB forwarding
        """
        try:
            if self.device_ws and not self.device_ws.closed:
                await self.device_ws.close()

            if self._session:
                await self._session.close()

            if self.device_id and self.local_port:
                remove_process = await asyncio.create_subprocess_exec(
                    "adb",
                    "-s",
                    self.device_id,
                    "forward",
                    "--remove",
                    f"tcp:{self.local_port}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await remove_process.communicate()

                if remove_process.returncode != 0:
                    self.logger.error(
                        f"Failed to remove port forwarding: {stderr.decode()}"
                    )
                else:
                    self.logger.info(
                        f"Successfully removed port forwarding for {self.device_id}"
                    )
        except Exception as e:
            self.logger.error(f"Error during cleanup: {str(e)}")

    async def close(self):
        """
        Closes all connections and cleans up resources
        """
        await self.cleanup()
