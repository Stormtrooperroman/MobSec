from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router
from app.core.app_manager import AsyncStorageService
from app.modules.chain_manager import ChainManager
from app.modules.module_manager import ModuleManager
from app.report_generator import start_report_generator, stop_report_generator
from app.core.settings_db import init_db
import os
import asyncio
import logging

logger = logging.getLogger(__name__)


module_manager = ModuleManager(
    redis_url=os.getenv('REDIS_URL'),
    modules_path=os.getenv('MODULES_PATH')
)

app = FastAPI(
    title="Mobile Security Testing Platform",
    description="A comprehensive platform for analyzing and security testing mobile applications.",
    version="0.1"
)
storage = AsyncStorageService()
chain_manager = ChainManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")

async def initialize_background_services():
    """Initialize modules and chains in the background."""
    try:
        if settings.EXTERNAL_MODULES_ENABLED:
            from app.modules.external_module_registry import module_registry
            logger.info("External modules registry initialized")
            
        await module_manager.start_modules()
        await chain_manager.start()
    except Exception as e:
        logger.error(f"Error during background initialization: {e}")

@app.on_event("startup")
async def startup_event():
    await init_db()
    
    await start_report_generator()
    
    asyncio.create_task(initialize_background_services())

@app.on_event("shutdown")
async def shutdown_event():
    await stop_report_generator()
    await module_manager.cleanup()
    
    if settings.EXTERNAL_MODULES_ENABLED:
        from app.modules.external_module_registry import module_registry
        module_registry.shutdown()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
