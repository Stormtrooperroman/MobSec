import json
import logging
import os

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from mitmproxy_manager import get_mitmproxy_manager, cleanup_mitmproxy_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)



app = FastAPI(title="Mitmproxy Module")


@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    logger.info("Mitmproxy WebSocket connected for device %s", device_id)

    mitmproxy_manager = await get_mitmproxy_manager(device_id)
    mitmproxy_manager.add_websocket(websocket)
    if not await mitmproxy_manager.start():
        await websocket.close(code=4000, reason="Failed to start Mitmproxy manager")
        return

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive":
                if "text" in message:
                    data = json.loads(message["text"])
                    data.setdefault("device_id", device_id)
                    await mitmproxy_manager.handle_message(
                        websocket, json.dumps(data)
                    )
    except WebSocketDisconnect:
        logger.info("Mitmproxy WebSocket disconnected for device %s", device_id)
    except Exception as e:
        logger.error("Error in Mitmproxy session for device %s: %s", device_id, str(e))
    finally:
        mitmproxy_manager.remove_websocket(websocket)
        await cleanup_mitmproxy_manager(device_id)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8091"))
    uvicorn.run(app, host="0.0.0.0", port=port)
