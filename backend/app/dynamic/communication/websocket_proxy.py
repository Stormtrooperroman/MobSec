import asyncio
import logging

import aiohttp
from fastapi import WebSocket
from app.dynamic.utils.adb_utils import execute_adb_command

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
        self._cleanup_done = False

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
            "Initializing WebSocket proxy for device '%s' (len: %s) on port %s",
            device_id,
            len(device_id),
            remote_port,
        )
        try:
            self.remote_port = remote_port
            self.local_port = remote_port

            await execute_adb_command(
                device_id=device_id,
                command=["forward", "--remove", f"tcp:{self.local_port}"],
            )

            _, stderr, returncode = await execute_adb_command(
                device_id=device_id,
                command=["forward", f"tcp:{self.local_port}", f"tcp:{self.remote_port}"],
            )

            if returncode != 0:
                raise RuntimeError(f"Failed to setup port forwarding: {stderr}")

            max_retries = 5
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    ws_url = f"ws://127.0.0.1:{self.local_port}/"
                    self.logger.info(
                        "Attempting WebSocket connection to %s (attempt %s)",
                        ws_url,
                        attempt + 1,
                    )

                    self.device_ws = await self._session.ws_connect(
                        ws_url, timeout=10, heartbeat=30
                    )

                    self.logger.info(
                        "WebSocket connection established for device %s "
                        "(local:%s -> remote:%s)",
                        device_id,
                        self.local_port,
                        self.remote_port,
                    )

                    self._start_device_message_handler()
                    return

                except (RuntimeError, ConnectionError, Exception) as e:
                    self.logger.warning(
                        "Connection attempt %s failed: %s",
                        attempt + 1,
                        str(e),
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
                        # Close session before raising error
                        if self._session:
                            try:
                                await self._session.close()
                                self._session = None
                            except Exception:
                                pass
                        raise

        except (RuntimeError, ConnectionError, Exception) as e:
            await self.cleanup()
            self.logger.error("Failed to initialize WebSocket proxy: %s", str(e))
            raise

    async def handle_client_message(self, message: str):
        """
        Handles a text message from the client
        """
        if self.device_ws and not self.device_ws.closed:
            try:
                self.logger.info(
                    "Sending text to device %s: %s", self.device_id, message
                )
                await self.device_ws.send_str(message)
            except (RuntimeError, ConnectionError) as e:
                self.logger.error("Error sending message to device: %s", str(e))
                await self.cleanup()

    async def handle_client_binary(self, data: bytes):
        """
        Handles a binary message from the client
        """
        if self.device_ws and not self.device_ws.closed:
            try:
                await self.device_ws.send_bytes(data)
            except (RuntimeError, ConnectionError) as e:
                self.logger.error("Error sending binary data to device: %s", str(e))
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
                        await self.client_ws.send_bytes(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        self.logger.error("WebSocket error: %s", str(msg.data))
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        self.logger.info("Device WebSocket closed")
                        break
            except (RuntimeError, ConnectionError) as e:
                self.logger.error("Error handling device messages: %s", str(e))
            finally:
                await self.cleanup()

        asyncio.create_task(handler())

    async def cleanup(self):
        """
        Cleans up all resources, including ADB forwarding
        """
        if self._cleanup_done:
            return

        try:
            # Close device WebSocket
            if self.device_ws and not self.device_ws.closed:
                try:
                    await self.device_ws.close()
                except Exception as e:
                    self.logger.warning("Error closing device WebSocket: %s", str(e))

            if self._session:
                try:
                    await self._session.close()
                except Exception as e:
                    self.logger.warning("Error closing session: %s", str(e))
                finally:
                    self._session = None

            if self.device_id and self.local_port:
                try:
                    _, stderr, returncode = await execute_adb_command(
                        device_id=self.device_id,
                        command=["forward", "--remove", f"tcp:{self.local_port}"],
                    )

                    if returncode != 0:
                        self.logger.error(
                            "Failed to remove port forwarding: %s",
                            stderr,
                        )
                    else:
                        self.logger.info(
                            "Successfully removed port forwarding for %s",
                            self.device_id,
                        )
                except Exception as e:
                    self.logger.error("Error removing port forwarding: %s", str(e))

        except Exception as e:
            self.logger.error("Error during cleanup: %s", str(e))
        finally:
            self._cleanup_done = True

    async def close(self):
        """
        Closes all connections and cleans up resources
        """
        await self.cleanup()
