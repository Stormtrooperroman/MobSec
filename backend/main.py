from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.router import api_router
from app.core.storage import AsyncStorageService
from app.modules.chain_manager import ChainManager
from app.modules.module_manager import ModuleManager
from app.report_generator import start_report_generator, stop_report_generator
import os


module_manager = ModuleManager(
    redis_url=os.getenv('REDIS_URL'),
    modules_path=os.getenv('MODULES_PATH')
)

app = FastAPI(
    title="Modular Security Analysis Platform",
    description="A modular security analysis platform for mobile applications",
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

@app.on_event("startup")
async def startup_event():
    await storage.init_db()
    await chain_manager.init_db()
    await module_manager.start_modules()
    await chain_manager.start()
    await start_report_generator()

@app.on_event("shutdown")
async def shutdown_event():
    await stop_report_generator()
    await module_manager.cleanup()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
