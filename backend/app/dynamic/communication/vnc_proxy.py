import asyncio
import logging

import aiohttp
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class VncProxy:
    """
    Proxies VNC WebSocket connections via SSH tunnel.
    Provides bidirectional data transfer between frontend and remote VNC server.
    """

    def __init__(self, client_ws: WebSocket):
        self.client_ws = client_ws
        self.vnc_ws = None
        self.device_id = None
        self.logger = logging.getLogger(__name__)
        self._session = None
        self._cleanup_done = False

    @classmethod
    async def create_proxy(
        cls, client_ws: WebSocket, device_id: str, vnc_url: str
    ) -> "VncProxy":
        """
        Creates a new VNC proxy for a WebSocket connection.

        Args:
            client_ws: FastAPI WebSocket from frontend
            device_id: Device identifier
            vnc_url: Remote VNC WebSocket URL (e.g., ws://host:5900)
        """
        proxy = cls(client_ws)
        await proxy.init(device_id, vnc_url)
        return proxy

    async def init(self, device_id: str, vnc_url: str):
        """
        Initializes the proxy, establishing a connection to the remote VNC server.
        """
        self._session = aiohttp.ClientSession()
        self.device_id = device_id
        self.logger.info(
            "Initializing VNC proxy for device '%s' to %s",
            device_id,
            vnc_url,
        )
        try:
            max_retries = 5
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    self.logger.info(
                        "Attempting VNC connection to %s (attempt %s)",
                        vnc_url,
                        attempt + 1,
                    )

                    self.vnc_ws = await self._session.ws_connect(
                        vnc_url, timeout=10, heartbeat=30
                    )

                    self.logger.info(
                        "VNC WebSocket connection established for device %s to %s",
                        device_id,
                        vnc_url,
                    )

                    self._start_vnc_message_handler()
                    return

                except (RuntimeError, ConnectionError, Exception) as e:
                    self.logger.warning(
                        "Connection attempt %s failed: %s",
                        attempt + 1,
                        str(e),
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                    else:
                        if self._session:
                            try:
                                await self._session.close()
                                self._session = None
                            except Exception:
                                pass
                        raise

        except Exception as e:
            await self.cleanup()
            self.logger.error("Failed to initialize VNC proxy: %s", str(e))
            raise

    async def handle_client_message(self, data: bytes):
        """
        Handles binary messages from the frontend client.
        VNC protocol is binary, so we mainly handle bytes.
        """
        if self.vnc_ws and not self.vnc_ws.closed:
            try:
                await self.vnc_ws.send_bytes(data)
            except (RuntimeError, ConnectionError) as e:
                self.logger.error("Error sending data to VNC server: %s", str(e))
                await self.cleanup()

    def _start_vnc_message_handler(self):
        """
        Starts the VNC message handler task that forwards messages from VNC to client.
        """

        async def handler():
            try:
                async for msg in self.vnc_ws:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        await self.client_ws.send_bytes(msg.data)
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        # VNC should be binary, but handle text just in case
                        await self.client_ws.send_text(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        self.logger.error("VNC WebSocket error: %s", str(msg.data))
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        self.logger.info("VNC WebSocket closed")
                        break
            except (RuntimeError, ConnectionError) as e:
                self.logger.error("Error handling VNC messages: %s", str(e))
            finally:
                await self.cleanup()

        asyncio.create_task(handler())

    async def cleanup(self):
        """
        Cleans up all resources.
        """
        if self._cleanup_done:
            return

        try:
            if self.vnc_ws and not self.vnc_ws.closed:
                try:
                    await self.vnc_ws.close()
                except Exception as e:
                    self.logger.warning("Error closing VNC WebSocket: %s", str(e))

            if self._session:
                try:
                    await self._session.close()
                except Exception as e:
                    self.logger.warning("Error closing session: %s", str(e))
                finally:
                    self._session = None

            self._cleanup_done = True
            self.logger.info(
                "VNC proxy cleanup completed for device %s", self.device_id
            )

        except Exception as e:
            self.logger.error("Error during VNC proxy cleanup: %s", str(e))

    async def close(self):
        """
        Closes the VNC proxy connection.
        """
        await self.cleanup()
