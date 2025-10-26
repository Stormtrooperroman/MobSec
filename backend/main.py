from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router
from app.core.app_manager import AsyncStorageService
from app.modules.chain_manager import ChainManager
from app.modules.module_manager import ModuleManager
from app.dynamic.device_management.emulator_manager import EmulatorManager
from app.report_generator import start_report_generator, stop_report_generator
from app.core.settings_db import init_db
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

module_manager = ModuleManager(
    redis_url=os.getenv("REDIS_URL"), modules_path=os.getenv("MODULES_PATH")
)

emulator_manager = EmulatorManager(
    redis_url=os.getenv("REDIS_URL"),
    emulators_path=os.getenv("EMULATORS_PATH", "/app/emulators"),
)

app = FastAPI(
    title="Mobile Security Testing Platform",
    description="A comprehensive platform for analyzing and security testing mobile applications.",
    version="0.1",
)
storage = AsyncStorageService()
chain_manager = ChainManager()

# Configure CORS for both HTTP and WebSocket
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(api_router)  # HTTP endpoints (includes WebSocket endpoints)


async def initialize_background_services():
    """Initialize modules, chains, and emulators in the background."""
    try:
        if settings.EXTERNAL_MODULES_ENABLED:
            from app.modules.external_module_registry import module_registry

        await module_manager.start_modules()
        await chain_manager.start()

        await emulator_manager.start_active_emulators()

    except Exception as e:
        logger.error(f"Error during background initialization: {e}")


@app.on_event("startup")
async def startup_event():
    await init_db()

    await start_report_generator()

    asyncio.create_task(initialize_background_services())


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Starting shutdown sequence...")

    try:
        await emulator_manager.cleanup()

        await stop_report_generator()

        await module_manager.cleanup()

        if settings.EXTERNAL_MODULES_ENABLED:
            from app.modules.external_module_registry import module_registry

            module_registry.shutdown()
            logger.info("External modules registry shutdown")

        logger.info("Shutdown sequence completed successfully")

    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
