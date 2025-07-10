import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from redis import Redis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.core.config import settings
from app.models.external_module import ExternalModule, ModuleStatus
from app.core.settings_db import AsyncSessionLocal

logger = logging.getLogger(__name__)


class ExternalModuleRegistry:

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ExternalModuleRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self.health_check_interval = settings.MODULES_HEALTH_CHECK_INTERVAL

        if settings.EXTERNAL_MODULES_ENABLED:
            loop = asyncio.get_event_loop()
            self._health_check_task = loop.create_task(self._health_check_loop())

        self._initialized = True

    async def register_module(self, module_data: dict) -> dict:
        """
        Register a new external module or update an existing one
        """
        if not settings.EXTERNAL_MODULES_ENABLED:
            raise HTTPException(
                status_code=403, detail="External modules support is disabled"
            )

        module_id = module_data["module_id"]

        max_retries = 3
        retry_delay = 5
        is_healthy = False

        for attempt in range(max_retries):
            is_healthy = await self._check_module_health(module_data["healthcheck_url"])
            if is_healthy:
                break
            if attempt < max_retries - 1:
                logger.info(
                    f"Health check failed for {module_id}, attempt {attempt + 1}/{max_retries}. Retrying in {retry_delay} seconds..."
                )
                await asyncio.sleep(retry_delay)

        logger.info(f"Health: {is_healthy}")

        module_dict = {
            "module_id": module_id,
            "base_url": module_data["base_url"],
            "config": module_data["config"],
            "healthcheck_url": module_data.get("healthcheck_url"),
            "registered_at": datetime.now(timezone.utc),
            "last_heartbeat": datetime.now(timezone.utc),
            "status": ModuleStatus.ACTIVE if is_healthy else ModuleStatus.ERROR,
            "error_message": None if is_healthy else "Health check failed",
        }

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExternalModule).where(ExternalModule.module_id == module_id)
            )
            existing_module = result.scalars().first()

            if existing_module:
                for key, value in module_dict.items():
                    setattr(existing_module, key, value)
            else:
                db_module = ExternalModule.from_dict(module_dict)
                session.add(db_module)

            await session.commit()

        logger.info(
            f"Module {module_id} {'registered successfully' if is_healthy else 'registered with errors'}"
        )
        return module_dict

    async def get_module(self, module_id: str) -> Optional[dict]:
        """Get module information by its ID"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExternalModule).where(ExternalModule.module_id == module_id)
            )
            db_module = result.scalars().first()

            if db_module:
                return db_module.to_dict()

        return None

    async def is_module_available(self, module_id: str) -> bool:
        """Check if module is available"""
        module = await self.get_module(module_id)
        if not module:
            return False

        return module["status"] == ModuleStatus.ACTIVE

    async def _check_module_health(self, health_url: str) -> bool:
        """Check module health via HTTP request using httpx"""
        logger.debug(f"Checking module health at URL: {health_url}")
        try:
            health_url_str = str(health_url)

            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    response = await client.get(health_url_str)

                    if response.status_code == 200:
                        logger.info(
                            f"Module {health_url} is healthy. Status: {response.status_code}"
                        )
                        return True
                    else:
                        logger.warning(
                            f"Module health check failed {health_url}. Status: {response.status_code}, Response: {response.text}"
                        )
                        return False
                except httpx.ConnectError as e:
                    logger.warning(
                        f"Connection error to module {health_url}: {e.__class__.__name__} - {str(e)}"
                    )
                    return False
                except httpx.TimeoutException as e:
                    logger.warning(
                        f"Timeout connecting to module {health_url}: {e.__class__.__name__} - {str(e)}"
                    )
                    return False

        except Exception as e:
            logger.error(f"Unexpected error checking module health {health_url}: {e}")
            return False

    async def update_module_heartbeat(self, module_id: str) -> bool:
        """Update the last contact time with the module"""
        module = await self.get_module(module_id)
        if not module:
            return False

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExternalModule).where(ExternalModule.module_id == module_id)
            )
            db_module = result.scalars().first()

            if db_module:
                db_module.last_heartbeat = datetime.now(timezone.utc)
                db_module.status = ModuleStatus.ACTIVE
                await session.commit()
                return True

            return False

    async def _health_check_loop(self):
        """Background task for periodic module health checks"""
        while True:
            try:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(select(ExternalModule))
                    db_modules = result.scalars().all()

                for db_module in db_modules:
                    time_since_last_heartbeat = (
                        datetime.now(timezone.utc) - db_module.last_heartbeat
                    ).total_seconds()
                    if time_since_last_heartbeat > self.health_check_interval:
                        health_url = db_module.healthcheck_url
                        is_healthy = await self._check_module_health(health_url)

                        async with AsyncSessionLocal() as session:
                            result = await session.execute(
                                select(ExternalModule).where(
                                    ExternalModule.module_id == db_module.module_id
                                )
                            )
                            module = result.scalars().first()

                            if module:
                                old_status = module.status
                                module.status = (
                                    ModuleStatus.ACTIVE
                                    if is_healthy
                                    else ModuleStatus.ERROR
                                )
                                module.last_heartbeat = datetime.now(timezone.utc)
                                if not is_healthy:
                                    module.error_message = "Health check failed"
                                else:
                                    module.error_message = None
                                await session.commit()

                                if old_status != module.status:
                                    logger.info(
                                        f"Module {db_module.module_id} status changed from {old_status} to {module.status}"
                                    )

                        logger.debug(
                            f"Health check for module {db_module.module_id}: {'healthy' if is_healthy else 'unhealthy'}"
                        )

            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

            await asyncio.sleep(self.health_check_interval)

    async def list_modules(self, active_only: bool = False) -> List[dict]:
        """Get a list of all registered modules"""
        async with AsyncSessionLocal() as session:
            query = select(ExternalModule)
            if active_only:
                query = query.where(ExternalModule.status == ModuleStatus.ACTIVE)

            result = await session.execute(query)
            db_modules = result.scalars().all()

            return [module.to_dict() for module in db_modules]

    async def deregister_module(self, module_id: str) -> bool:
        """Remove a module from the registry"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ExternalModule).where(ExternalModule.module_id == module_id)
            )
            db_module = result.scalars().first()

            if not db_module:
                return False

            await session.delete(db_module)
            await session.commit()

        logger.info(f"Module {module_id} removed from registry")
        return True

    def shutdown(self):
        """Stop background tasks on shutdown"""
        if hasattr(self, "_health_check_task"):
            self._health_check_task.cancel()


module_registry = ExternalModuleRegistry()
