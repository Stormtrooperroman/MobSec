import asyncio
import logging
import os
import threading
from typing import Any, Dict, List, Optional

import yaml
from app.core.database_manager import db_manager
from sqlalchemy import select

from app.services.docker_service import DockerService
from app.models.emulator import Emulator
from app.dynamic.device_management.android_emulator_manager import (
    AndroidEmulatorManager,
)
from app.dynamic.device_management.aurora_emulator_manager import AuroraEmulatorManager

logger = logging.getLogger(__name__)


class EmulatorManager:
    _instance: "EmulatorManager" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, redis_url: str, emulators_path: str):
        if getattr(self, "_initialized", False):
            return

        self.redis_url = redis_url
        self.emulators_path = emulators_path
        self.docker_service = DockerService.get_instance()
        self.emulators_config = self._load_emulators_config()
        self.async_session = db_manager.session_factory

        self.android_manager = AndroidEmulatorManager(
            emulators_path, self.docker_service, redis_url
        )
        self.aurora_manager = AuroraEmulatorManager(
            emulators_path, self.docker_service, redis_url
        )
        self.managers = {
            "android": self.android_manager,
            "aurora": self.aurora_manager,
        }

        self._initialized = True

    @classmethod
    def get_instance(
        cls, redis_url: Optional[str] = None, emulators_path: Optional[str] = None
    ) -> "EmulatorManager":
        if cls._instance is None:
            if redis_url is None or emulators_path is None:
                raise ValueError(
                    "EmulatorManager.get_instance requires redis_url and "
                    "emulators_path on first call"
                )
            return cls(redis_url, emulators_path)
        return cls._instance

    def _load_emulators_config(self) -> Dict[str, Any]:
        """Load emulator configurations"""
        configs = {}
        try:
            for root, _, files in os.walk(self.emulators_path):
                if "config.yaml" in files:
                    config_path = os.path.join(root, "config.yaml")
                    rel_path = os.path.relpath(root, self.emulators_path)
                    emulator_name = rel_path.replace(os.sep, "_")

                    with open(config_path, encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                        config["path"] = root
                        configs[emulator_name] = config
        except Exception as e:
            logger.error("Error loading emulator configs: %s", e)
        return configs

    def _get_manager_for_config(self, config: Dict[str, Any]) -> str:
        """Determine which manager to use for a config"""
        os_type = config.get("os_type", "android")
        if os_type not in self.managers:
            logger.warning("Unknown OS type %s, defaulting to android", os_type)
            return "android"
        return os_type

    async def _register_emulator(self, emulator_name: str, config: dict) -> None:
        """Register emulator in database"""
        async with self.async_session() as session:
            try:
                stmt = select(Emulator).where(Emulator.name == emulator_name)
                result = await session.execute(stmt)
                existing_emulator = result.scalar_one_or_none()

                version = str(config.get("version", "1.0.0"))
                os_type = config.get("os_type", "android")

                if existing_emulator:
                    existing_emulator.version = version
                    existing_emulator.description = config.get("description")
                    existing_emulator.config = config
                else:
                    emulator = Emulator(
                        name=emulator_name,
                        version=version,
                        description=config.get("description"),
                        config=config,
                        os_type=os_type,
                    )
                    session.add(emulator)

                await session.commit()
            except Exception as e:
                logger.error("Failed to register emulator %s: %s", emulator_name, e)
                await session.rollback()

    async def start_emulator(self, emulator_name: str) -> Dict[str, Any]:
        """Start emulator using appropriate OS-specific manager"""
        logger.info("Starting emulator %s...", emulator_name)

        if emulator_name not in self.emulators_config:
            raise ValueError(f"Emulator {emulator_name} not found")

        config = self.emulators_config[emulator_name]

        await self._register_emulator(emulator_name, config)

        manager_type = self._get_manager_for_config(config)
        manager = self.managers[manager_type]

        try:
            result = await manager.start_emulator(emulator_name, config)

            # Update database with mapped ports and container info
            await self._update_emulator_status(
                emulator_name,
                "running",
                result["container_id"],
                result.get("mapped_ports", {}),
            )

            # Connect to emulator (manager-specific logic)
            await manager.connect_to_emulator(
                emulator_name,
                result["container_id"],
                config,
                mapped_ports=result.get("mapped_ports", {}),
            )

            return result
        except Exception as e:
            logger.error("Failed to start emulator %s: %s", emulator_name, e)
            await self._update_emulator_status(emulator_name, "failed")
            raise

    async def stop_emulator(self, emulator_name: str) -> bool:
        """Stop emulator"""
        try:
            async with self.async_session() as session:
                stmt = select(Emulator).where(Emulator.name == emulator_name)
                result = await session.execute(stmt)
                emulator = result.scalar_one_or_none()

                if emulator and emulator.container_id:
                    await self.docker_service.stop_container(emulator.container_id)
                    logger.info("Stopped emulator %s", emulator_name)

            await self._update_emulator_status(
                emulator_name, "stopped", container_id=None, mapped_ports=None
            )
            return True

        except Exception as e:
            logger.error("Error stopping emulator %s: %s", emulator_name, e)
            return False

    async def _update_emulator_status(
        self,
        emulator_name: str,
        status: str,
        container_id: str = None,
        mapped_ports: Dict[str, int] = None,
    ) -> None:
        """Update emulator status in database"""
        async with self.async_session() as session:
            stmt = select(Emulator).where(Emulator.name == emulator_name)
            result = await session.execute(stmt)
            emulator = result.scalar_one_or_none()

            if emulator:
                emulator.status = status
                emulator.container_id = container_id
                emulator.mapped_ports = mapped_ports
                await session.commit()

    async def get_emulator_status(self, emulator_name: str) -> Dict[str, Any]:
        """Get emulator status and details"""
        async with self.async_session() as session:
            stmt = select(Emulator).where(Emulator.name == emulator_name)
            result = await session.execute(stmt)
            emulator = result.scalar_one_or_none()

            if not emulator:
                return {"error": f"Emulator {emulator_name} not found"}

            return {
                "name": emulator.name,
                "status": emulator.status,
                "container_id": emulator.container_id,
                "mapped_ports": emulator.mapped_ports or {},
                "version": emulator.version,
                "os_type": emulator.os_type,
            }

    async def list_emulators(self) -> List[Dict[str, Any]]:
        """List all emulators with details"""
        async with self.async_session() as session:
            stmt = select(Emulator)
            result = await session.execute(stmt)
            emulators = result.scalars().all()

            emulator_list = []
            for emulator in emulators:
                emulator_data = {
                    "name": emulator.name,
                    "status": emulator.status,
                    "container_id": emulator.container_id,
                    "mapped_ports": emulator.mapped_ports or {},
                    "version": emulator.version,
                    "description": emulator.description,
                    "os_type": emulator.os_type,
                    "config": emulator.config,
                }
                emulator_list.append(emulator_data)

            return emulator_list

    async def get_running_emulators(self) -> List[Dict[str, Any]]:
        """Get only running emulators"""
        all_emulators = await self.list_emulators()
        return [e for e in all_emulators if e["status"] == "running"]

    async def get_running_emulators_by_os(self, os_type: str) -> List[Dict[str, Any]]:
        """Get running emulators for specific OS type"""
        running = await self.get_running_emulators()
        return [e for e in running if e["os_type"] == os_type]

    async def get_emulator_by_udid(self, udid: str) -> Optional[Dict[str, Any]]:
        """Get emulator by localhost UDID (127.0.0.1:port)"""
        if not udid.startswith("127.0.0.1:"):
            return None

        running = await self.get_running_emulators()
        for emulator in running:
            os_type = emulator.get("os_type")
            mapped_ports = emulator.get("mapped_ports", {})

            if os_type == "android":
                adb_port = mapped_ports.get("adb", 5555)
                emulator_udid = f"127.0.0.1:{adb_port}"
            elif os_type == "aurora":
                ssh_port = mapped_ports.get("ssh", 2223)
                emulator_udid = f"127.0.0.1:{ssh_port}"
            else:
                continue

            if emulator_udid == udid:
                return emulator

        return None

    async def cleanup(self) -> None:
        """Clean up all emulators"""
        emulators = await self.list_emulators()
        running = [e for e in emulators if e["status"] == "running"]

        for emulator in running:
            await self.stop_emulator(emulator["name"])

        if running:
            logger.info("Cleaned up %d emulators", len(running))

    async def start_active_emulators(self) -> None:
        """Start emulators marked as active in config"""
        logger.info("Starting active emulators...")

        try:
            for emulator_name, config in self.emulators_config.items():
                await self._register_emulator(emulator_name, config)

            active_emulators = [
                name
                for name, config in self.emulators_config.items()
                if config.get("active", False)
            ]

            if active_emulators:
                logger.info("Starting %d active emulators", len(active_emulators))
                tasks = [self.start_emulator(name) for name in active_emulators]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                started = sum(1 for r in results if not isinstance(r, Exception))
                logger.info(
                    "Started %d/%d emulators successfully",
                    started,
                    len(active_emulators),
                )

                for name, result in zip(active_emulators, results):
                    if isinstance(result, Exception):
                        logger.error("Failed to start emulator %s: %s", name, result)
            else:
                logger.info("No active emulators configured")

        except Exception as e:
            logger.error("Error starting active emulators: %s", e)
