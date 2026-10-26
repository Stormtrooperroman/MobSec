import logging

from fastapi import WebSocket

from frida_scripts.database import init_db
from frida_manager import FridaManager
from mobsec_modules_library.dynamic import (
    BaseModuleManager,
    create_module_app,
    run_module_server,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class FridaModuleManager(BaseModuleManager):

    def __init__(self, websocket: WebSocket, device_id: str):
        self._manager = FridaManager(websocket, device_id)

    async def start(self) -> bool:
        return await self._manager.start()

    async def handle_message(
        self, websocket: WebSocket, device_id: str, text: str
    ) -> None:
        await self._manager.handle_message(text)

    async def stop(self) -> None:
        await self._manager.stop()


async def manager_factory(websocket: WebSocket, device_id: str) -> FridaModuleManager:
    return FridaModuleManager(websocket, device_id)


app = create_module_app("Frida Module", manager_factory, lifespan_init=init_db)

if __name__ == "__main__":
    run_module_server(app, default_port=8090)
