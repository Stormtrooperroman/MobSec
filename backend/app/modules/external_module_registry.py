import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from redis import Redis
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import httpx

from app.core.config import settings
from app.models.module import Module, ModuleStatus, ModuleSource, ModuleType
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
        if hasattr(self, "_initialized") and self._initialized:
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

        name = module_data["name"]

        max_retries = 3
        retry_delay = 5
        is_healthy = False

        for attempt in range(max_retries):
            is_healthy = await self._check_module_health(module_data["healthcheck_url"])
            if is_healthy:
                break
            if attempt < max_retries - 1:
                logger.info(
                    "Health check failed for %s, attempt %s/%s. Retrying in %s seconds...",
                    name,
                    attempt + 1,
                    max_retries,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)

        logger.info("Health: %s", is_healthy)
        module_type = (
            ModuleType.DYNAMIC
            if module_data["config"].get("type") == "dynamic"
            else ModuleType.STATIC
        )
        module_dict = {
            "name": name,
            "base_url": module_data["base_url"],
            "config": module_data["config"],
            "healthcheck_url": module_data.get("healthcheck_url"),
            "registered_at": datetime.now(timezone.utc),
            "last_heartbeat": datetime.now(timezone.utc),
            "status": ModuleStatus.ACTIVE if is_healthy else ModuleStatus.ERROR,
            "error_message": None if is_healthy else "Health check failed",
            "source": ModuleSource.EXTERNAL,
            "module_type": module_type,
        }

        async with AsyncSessionLocal() as session:
            existing_module = await self._get_db_module(session, name)

            if existing_module:
                for key, value in module_dict.items():
                    setattr(existing_module, key, value)
            else:
                db_module = Module.from_dict(module_dict)
                session.add(db_module)

            await session.commit()

        status_msg = (
            "registered successfully" if is_healthy else "registered with errors"
        )
        logger.info("Module %s %s", name, status_msg)
        return module_dict

    async def _get_db_module(
        self, session: AsyncSession, name: str
    ) -> Optional[Module]:
        result = await session.execute(select(Module).where(Module.name == name))
        return result.scalars().first()

    async def get_module(self, name: str) -> Optional[dict]:
        """Get module information by its ID"""
        async with AsyncSessionLocal() as session:
            db_module = await self._get_db_module(session, name)

            if db_module:
                return db_module.to_dict()

        return None

    async def is_module_available(self, name: str) -> bool:
        """Check if module is available"""
        module = await self.get_module(name)
        if not module:
            return False
        return module["status"] == ModuleStatus.ACTIVE

    async def _check_module_health(self, health_url: str) -> bool:
        """Check module health via HTTP request using httpx"""
        logger.debug("Checking module health at URL: %s", health_url)
        try:
            health_url_str = str(health_url)

            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    response = await client.get(health_url_str)

                    if response.status_code == 200:
                        logger.info(
                            "Module %s is healthy. Status: %s",
                            health_url,
                            response.status_code,
                        )
                        return True
                    logger.warning(
                        "Module health check failed %s. Status: %s, Response: %s",
                        health_url,
                        response.status_code,
                        response.text,
                    )
                    return False
                except httpx.ConnectError as e:
                    logger.warning(
                        "Connection error to module %s: %s - %s",
                        health_url,
                        e.__class__.__name__,
                        str(e),
                    )
                    return False
                except httpx.TimeoutException as e:
                    logger.warning(
                        "Timeout connecting to module %s: %s - %s",
                        health_url,
                        e.__class__.__name__,
                        str(e),
                    )
                    return False

        except Exception as e:
            logger.error(
                "Unexpected error checking module health %s: %s", health_url, e
            )
            return False

    async def update_module_heartbeat(self, name: str) -> bool:
        """Update the last contact time with the module"""
        module = await self.get_module(name)
        if not module:
            return False

        async with AsyncSessionLocal() as session:
            db_module = await self._get_db_module(session, name)

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
                    result = await session.execute(select(Module))
                    db_modules = result.scalars().all()

                for db_module in db_modules:
                    time_since_last_heartbeat = (
                        datetime.now(timezone.utc) - db_module.last_heartbeat
                    ).total_seconds()
                    if time_since_last_heartbeat > self.health_check_interval:
                        health_url = db_module.healthcheck_url
                        is_healthy = await self._check_module_health(health_url)

                        async with AsyncSessionLocal() as session:
                            module = await self._get_db_module(session, db_module.name)

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
                                        "Module %s status changed from %s to %s",
                                        db_module.name,
                                        old_status,
                                        module.status,
                                    )

                        health_status = "healthy" if is_healthy else "unhealthy"
                        logger.debug(
                            "Health check for module %s: %s",
                            db_module.name,
                            health_status,
                        )

            except Exception as e:
                logger.error("Error in health check loop: %s", e)

            await asyncio.sleep(self.health_check_interval)

    async def list_modules(
        self, module_type: str | None = None, active_only: bool = False
    ) -> List[dict]:
        """Get a list of all registered modules"""
        modules_info = []
        async with AsyncSessionLocal() as session:
            query = select(Module).where(Module.source == ModuleSource.EXTERNAL)
            if active_only:
                query = query.where(Module.status == ModuleStatus.ACTIVE)
            if module_type is not None:
                query = query.where(Module.module_type == module_type)

            result = await session.execute(query)
            db_modules = result.scalars().all()

            for module in db_modules:
                module_dict = module.to_dict()
                module_info = {
                    "id": module_dict["name"],
                    "name": module_dict["config"].get("name", module_dict["name"]),
                    "description": module_dict["config"].get(
                        "description", "No description available"
                    ),
                    "active": module_dict["status"] == ModuleStatus.ACTIVE,
                    "is_external": True,
                    "version": module_dict["config"].get("version"),
                    "input_formats": module_dict["config"].get("input_formats", []),
                    "module_type": module_dict.get("type"),
                }
                if "map_name" in module_dict["config"]:
                    module_info["map_name"] = module_dict["config"].get("map_name")

                if (
                    module_dict["config"].get("type") == ModuleType.DYNAMIC
                    and "view" in module_dict["config"]
                ):
                    module_info["view"] = module_dict["config"].get("view")

                modules_info.append(module_info)

            return modules_info

    async def deregister_module(self, name: str) -> bool:
        """Remove a module from the registry"""
        async with AsyncSessionLocal() as session:
            db_module = await self._get_db_module(session, name)

            if not db_module:
                return False

            await session.delete(db_module)
            await session.commit()

        logger.info("Module %s removed from registry", name)
        return True

    def shutdown(self):
        """Stop background tasks on shutdown"""
        if hasattr(self, "_health_check_task"):
            self._health_check_task.cancel()


module_registry = ExternalModuleRegistry()
