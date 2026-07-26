import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from database import init_db
from frida_manager import FridaManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Frida Module", lifespan=lifespan)


@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    logger.info("Frida WebSocket connected for device %s", device_id)

    frida_manager = FridaManager(websocket, device_id)
    if not await frida_manager.start():
        await websocket.close(code=4000, reason="Failed to start Frida manager")
        return

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive":
                if "text" in message:
                    await frida_manager.handle_message(message["text"])
    except WebSocketDisconnect:
        logger.info("Frida WebSocket disconnected for device %s", device_id)
    except Exception as e:
        logger.error("Error in Frida session for device %s: %s", device_id, str(e))
    finally:
        await frida_manager.stop()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
