import json
import logging

from fastapi import WebSocket

from mitmproxy_manager import cleanup_mitmproxy_manager, get_mitmproxy_manager
from mobsec_modules_library.dynamic import (
    BaseModuleManager,
    create_module_app,
    run_module_server,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class MitmproxyModuleManager(BaseModuleManager):

    def __init__(self, manager, websocket: WebSocket, device_id: str):
        self._manager = manager
        self._websocket = websocket
        self._device_id = device_id

    async def start(self) -> bool:
        return await self._manager.start()

    async def handle_message(
        self, websocket: WebSocket, device_id: str, text: str
    ) -> None:
        data = json.loads(text)
        data.setdefault("device_id", device_id)
        await self._manager.handle_message(websocket, json.dumps(data))

    async def stop(self) -> None:
        self._manager.remove_websocket(self._websocket)
        await cleanup_mitmproxy_manager(self._device_id)


async def manager_factory(
    websocket: WebSocket, device_id: str
) -> MitmproxyModuleManager:
    manager = await get_mitmproxy_manager(device_id)
    manager.add_websocket(websocket)
    return MitmproxyModuleManager(manager, websocket, device_id)


app = create_module_app("Mitmproxy Module", manager_factory)

if __name__ == "__main__":
    run_module_server(app, default_port=8091)
