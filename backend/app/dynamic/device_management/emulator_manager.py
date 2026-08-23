import asyncio
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

from docker.types import Mount
import yaml
from app.core.database_manager import db_manager
from sqlalchemy import select

from app.services.docker_service import DockerService

from app.dynamic.utils.adb_utils import get_adb_env, ensure_adb_server
from app.models.emulator import Emulator

logger = logging.getLogger(__name__)


class EmulatorManager:

    def __init__(self, redis_url: str, emulators_path: str):
        self.redis_url = redis_url
        self.emulators_path = emulators_path
        self.docker_service = DockerService()
        self.emulators_config = self._load_emulators_config()
        self.base_ports = {"adb": 5555, "frida": 27042, "scrcpy": 8886}

        self.async_session = db_manager.session_factory

    async def _wait_for_android_boot(
        self, host: str, port: int, timeout: int = 120
    ) -> bool:
        """Wait for Android system to fully boot"""
        logger.info("Waiting for Android system to boot...")

        env = get_adb_env()
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                connect_result = subprocess.run(
                    ["adb", "connect", f"{host}:{port}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=env,
                    check=False,
                )

                if connect_result.returncode != 0:
                    await asyncio.sleep(2)
                    continue

                devices_result = subprocess.run(
                    ["adb", "devices", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=env,
                    check=False,
                )

                if (
                    devices_result.returncode == 0
                    and f"{host}:{port}" in devices_result.stdout
                ):
                    boot_check = subprocess.run(
                        [
                            "adb",
                            "-s",
                            f"{host}:{port}",
                            "shell",
                            "getprop",
                            "sys.boot_completed",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        env=env,
                        check=False,
                    )

                    if boot_check.returncode == 0 and "1" in boot_check.stdout.strip():
                        logger.info("Android system ready")
                        return True

                await asyncio.sleep(3)

            except Exception:
                await asyncio.sleep(2)

        logger.warning("Timeout waiting for Android boot")
        return False

    async def _adb_connect(self, host: str, port: int) -> bool:
        """Connect to emulator via ADB"""
        try:
            await ensure_adb_server()

            env = get_adb_env()

            check_result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                check=False,
            )

            if check_result.returncode == 0 and f"{host}:{port}" in check_result.stdout:
                logger.info("Device already connected")
                return True

            if not await self._wait_for_android_boot(host, port):
                return False

            result = subprocess.run(
                ["adb", "connect", f"{host}:{port}"],
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
                check=False,
            )

            success = (
                result.returncode == 0
                or "connected to" in result.stdout.lower()
                or "already connected" in result.stdout.lower()
            )
            if success:
                logger.info("Successfully connected via ADB")
            else:
                logger.warning("Failed to connect via ADB: %s", result.stderr)

            return success

        except Exception as e:
            logger.error("Error connecting via ADB: %s", e)
            return False

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

    def _get_available_ports(self, emulator_name: str) -> Dict[str, int]:
        """Get available external ports for emulator"""
        numbers = re.findall(r"\d+", emulator_name)
        if numbers:
            offset = int(numbers[-1])
        else:
            offset = abs(hash(emulator_name)) % 100

        return {
            "adb": self.base_ports["adb"] + offset,
            "frida": self.base_ports["frida"] + offset,
            "scrcpy": self.base_ports["scrcpy"] + offset,
        }

    async def _get_container_ip(self, container_id: str) -> Optional[str]:
        """Get container IP address"""
        return await self.docker_service.get_container_ip(
            container_id, network_name="mobsec_app_network"
        )

    async def _register_emulator(self, emulator_name: str, config: dict):
        """Register emulator in database"""
        async with self.async_session() as session:
            try:
                stmt = select(Emulator).where(Emulator.name == emulator_name)
                result = await session.execute(stmt)
                existing_emulator = result.scalar_one_or_none()

                version = str(
                    config.get("version", config.get("android_version", "12.0.0"))
                )
                ports = self._get_available_ports(emulator_name)

                if existing_emulator:
                    existing_emulator.version = version
                    existing_emulator.description = config.get("description")
                    existing_emulator.config = config
                    existing_emulator.ports = ports
                    emulator = existing_emulator
                else:
                    emulator = Emulator(
                        name=emulator_name,
                        version=version,
                        description=config.get("description"),
                        config=config,
                        ports=ports,
                    )
                    session.add(emulator)

                await session.commit()
                await session.refresh(emulator)

                return {
                    "name": emulator.name,
                    "version": emulator.version,
                    "description": emulator.description,
                    "config": emulator.config,
                    "ports": emulator.ports,
                    "status": emulator.status,
                }
            except Exception as e:
                logger.error("Failed to register emulator %s: %s", emulator_name, e)
                await session.rollback()
                raise

    async def _ensure_volume_subpath(self, volume_name: str, subpath: str) -> None:
        """Ensure a subdirectory exists inside a named volume before subpath-mounting it."""
        await self.docker_service.run_container(
            image="busybox",
            name=f"mobsec_volume_init_{subpath}",
            command=["mkdir", "-p", f"/vol/{subpath}"],
            volumes={volume_name: {"bind": "/vol", "mode": "rw"}},
            remove=True,
            detach=False,
        )

    async def start_emulator(self, emulator_name: str) -> Dict[str, Any]:
        """Start emulator"""
        logger.info("Starting emulator %s...", emulator_name)

        if emulator_name not in self.emulators_config:
            raise ValueError(f"Emulator {emulator_name} not found")

        config = self.emulators_config[emulator_name]

        await self._register_emulator(emulator_name, config)

        container_name = f"emulator_{emulator_name}"
        image_name = f"mobsec_emulator_{emulator_name}"
        ports = self._get_available_ports(emulator_name)

        emulator_path = config.get("path")
        dockerfile_path = os.path.join(emulator_path, "Dockerfile")

        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

        logger.info("Building Docker image for %s...", emulator_name)
        await self.docker_service.build_image(emulator_path, image_name)

        port_bindings = {}
        for service, external_port in ports.items():
            internal_port = self.base_ports[service]
            port_bindings[f"{internal_port}/tcp"] = external_port

        await self._ensure_volume_subpath("mobsec_shared_data", emulator_name)

        container = await self.docker_service.run_container(
            image=image_name,
            name=container_name,
            privileged=True,
            network="mobsec_app_network",
            ports=port_bindings,
            environment={"REDIS_URL": self.redis_url, "EMULATOR_NAME": emulator_name},
            mounts=[
                Mount(
                    target="/data",
                    source="mobsec_shared_data",
                    type="volume",
                    subpath=emulator_name,
                )
            ],
        )

        await self._update_emulator_status(emulator_name, "running", container.id)

        logger.info("Container started for %s", emulator_name)
        await self.connect_to_emulator(emulator_name)
        return {
            "name": emulator_name,
            "status": "running",
            "container_id": container.id,
        }

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

                await self._update_emulator_status(emulator_name, "stopped", None)
                return True

        except Exception as e:
            logger.error("Error stopping emulator %s: %s", emulator_name, e)
            return False

    async def _update_emulator_status(
        self, emulator_name: str, status: str, container_id: str = None
    ):
        """Update emulator status"""
        async with self.async_session() as session:
            stmt = select(Emulator).where(Emulator.name == emulator_name)
            result = await session.execute(stmt)
            emulator = result.scalar_one_or_none()

            if emulator:
                emulator.status = status
                if container_id is not None:
                    emulator.container_id = container_id
                await session.commit()

    async def get_emulator_status(self, emulator_name: str) -> Dict[str, Any]:
        """Get emulator status"""
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
                "ports": emulator.ports,
                "version": emulator.version,
            }

    async def list_emulators(self) -> List[Dict[str, Any]]:
        """List all emulators"""

        async with self.async_session() as session:
            stmt = select(Emulator).where(Emulator.active.is_(True))
            result = await session.execute(stmt)
            emulators = result.scalars().all()

            emulator_list = []
            for emulator in emulators:
                emulator_data = {
                    "name": emulator.name,
                    "status": emulator.status,
                    "container_id": emulator.container_id,
                    "ports": emulator.ports,
                    "version": emulator.version,
                    "description": emulator.description,
                    "config": emulator.config,
                }
                emulator_list.append(emulator_data)

            return emulator_list

    async def cleanup(self):
        """Clean up all emulators"""
        emulators = await self.list_emulators()
        for emulator in emulators:
            await self.stop_emulator(emulator["name"])
        if emulators:
            logger.info("All emulators cleaned up")

    async def start_active_emulators(self):
        """Start active emulators on startup"""
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
                logger.info("Starting %s active emulators", len(active_emulators))
                tasks = [
                    self.start_emulator(emulator_name)
                    for emulator_name in active_emulators
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                started = 0
                for emulator_name, result in zip(active_emulators, results):
                    if isinstance(result, Exception):
                        logger.error(
                            "Failed to start emulator %s: %s", emulator_name, result
                        )
                    else:
                        started += 1

                logger.info(
                    "Started %s/%s emulators successfully",
                    started,
                    len(active_emulators),
                )
            else:
                logger.info("No active emulators configured")

        except Exception as e:
            logger.error("Error starting active emulators: %s", e)

    async def connect_to_emulator(self, emulator_name: str) -> bool:
        """Connect to emulator via ADB"""
        status_data = await self.get_emulator_status(emulator_name)
        if "error" in status_data or status_data["status"] != "running":
            logger.warning("Emulator %s is not running", emulator_name)
            return False

        container_id = status_data.get("container_id")
        if not container_id:
            logger.warning("No container ID for emulator %s", emulator_name)
            return False

        container_ip = await self._get_container_ip(container_id)
        if not container_ip:
            logger.warning("Could not get container IP for emulator %s", emulator_name)
            return False

        logger.info("Connecting to emulator %s...", emulator_name)
        connection_result = await self._adb_connect(container_ip, 5555)

        if connection_result:
            logger.info("Successfully connected to emulator %s", emulator_name)
        else:
            logger.error("Failed to connect to emulator %s", emulator_name)

        return connection_result
