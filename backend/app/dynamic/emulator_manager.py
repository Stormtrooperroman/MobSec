import os
import logging
import asyncio
import subprocess
import docker
import docker.errors
import yaml
import socket
import re
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from redis import Redis
from app.models.emulator import Emulator, Base

logger = logging.getLogger(__name__)


class EmulatorManager:
    @staticmethod
    def get_adb_env():
        """Get environment variables for ADB commands"""
        env = os.environ.copy()
        return env

    def __init__(self, redis_url: str, emulators_path: str):
        self.redis_url = redis_url
        self.emulators_path = emulators_path
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.docker_client = docker.from_env()
        self.emulators_config = self._load_emulators_config()
        self.base_ports = {"adb": 5555, "frida": 27042, "scrcpy": 8886}
        self.adb_port = None

        database_url = os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://postgres:password@db:5432/mobsec_db"
        )
        self.engine = create_async_engine(database_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    def _find_free_port(self) -> int:
        """Find a free port"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("", 0))
        port = sock.getsockname()[1]
        sock.close()
        return port

    async def _ensure_adb_server(self) -> int:
        """Ensure ADB server is running and return port"""
        if self.adb_port:
            return self.adb_port

        try:
            result = subprocess.run(
                ["adb", "kill-server"], capture_output=True, text=True, timeout=10
            )
            logger.info("Killed existing ADB server")
            await asyncio.sleep(1)
        except Exception as e:
            pass

        try:
            result = subprocess.run(
                ["adb", "start-server"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.adb_port = 5037
                logger.info("ADB server started on port 5037")
                os.environ["ANDROID_ADB_SERVER_PORT"] = "5037"
                return 5037
            else:
                logger.warning(f"Failed to start ADB on standard port: {result.stderr}")
        except Exception as e:
            logger.warning(f"Failed to start ADB on standard port: {e}")

        dynamic_port = self._find_free_port()
        try:
            env = os.environ.copy()
            env["ANDROID_ADB_SERVER_PORT"] = str(dynamic_port)

            result = subprocess.run(
                ["adb", "start-server"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            if result.returncode == 0:
                self.adb_port = dynamic_port
                logger.info(f"ADB server started on port {dynamic_port}")
                os.environ["ANDROID_ADB_SERVER_PORT"] = str(dynamic_port)
                return dynamic_port
        except Exception as e:
            logger.warning(f"Failed to start ADB on dynamic port: {e}")

        logger.warning("Could not start ADB server, using default port 5037")
        self.adb_port = 5037
        os.environ["ANDROID_ADB_SERVER_PORT"] = "5037"
        return 5037

    async def _wait_for_android_boot(
        self, host: str, port: int, timeout: int = 120
    ) -> bool:
        """Wait for Android system to fully boot"""
        logger.info(f"Waiting for Android system to boot...")

        env = self.get_adb_env()
        start_time = asyncio.get_event_loop().time()

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                connect_result = subprocess.run(
                    ["adb", "connect", f"{host}:{port}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=env,
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
                    )

                    if boot_check.returncode == 0 and "1" in boot_check.stdout.strip():
                        logger.info(f"Android system ready")
                        return True

                await asyncio.sleep(3)

            except Exception as e:
                await asyncio.sleep(2)

        logger.warning(f"Timeout waiting for Android boot")
        return False

    async def _adb_connect(self, host: str, port: int) -> bool:
        """Connect to emulator via ADB"""
        try:
            await self._ensure_adb_server()

            env = self.get_adb_env()

            check_result = subprocess.run(
                ["adb", "devices"], capture_output=True, text=True, timeout=10, env=env
            )

            if check_result.returncode == 0 and f"{host}:{port}" in check_result.stdout:
                logger.info(f"Device already connected")
                return True

            if not await self._wait_for_android_boot(host, port):
                return False

            result = subprocess.run(
                ["adb", "connect", f"{host}:{port}"],
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
            )

            success = (
                result.returncode == 0
                or "connected to" in result.stdout.lower()
                or "already connected" in result.stdout.lower()
            )
            if success:
                logger.info(f"Successfully connected via ADB")
            else:
                logger.warning(f"Failed to connect via ADB: {result.stderr}")

            return success

        except Exception as e:
            logger.error(f"Error connecting via ADB: {e}")
            return False

    def _load_emulators_config(self) -> Dict[str, Any]:
        """Load emulator configurations"""
        configs = {}
        try:
            for root, dirs, files in os.walk(self.emulators_path):
                if "config.yaml" in files:
                    config_path = os.path.join(root, "config.yaml")
                    rel_path = os.path.relpath(root, self.emulators_path)
                    emulator_name = rel_path.replace(os.sep, "_")

                    with open(config_path) as f:
                        config = yaml.safe_load(f)
                        config["path"] = root
                        configs[emulator_name] = config
        except Exception as e:
            logger.error(f"Error loading emulator configs: {e}")
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

    def _get_container_ip(self, container_id: str) -> Optional[str]:
        """Get container IP address"""
        try:
            container = self.docker_client.containers.get(container_id)
            network_name = "mobsec_app_network"

            networks = container.attrs["NetworkSettings"]["Networks"]
            if network_name in networks:
                return networks[network_name]["IPAddress"]

            for network in networks.values():
                if network.get("IPAddress"):
                    return network["IPAddress"]

        except Exception as e:
            logger.error(f"Error getting container IP: {e}")

        return None

    async def _create_emulator_table(self):
        """Create emulator table if it doesn't exist"""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception as e:
            logger.error(f"Failed to create emulator table: {e}")
            raise

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
                logger.error(f"Failed to register emulator {emulator_name}: {e}")
                await session.rollback()
                raise

    async def start_emulator(self, emulator_name: str) -> Dict[str, Any]:
        """Start emulator"""
        logger.info(f"Starting emulator {emulator_name}...")

        if emulator_name not in self.emulators_config:
            raise ValueError(f"Emulator {emulator_name} not found")

        config = self.emulators_config[emulator_name]

        await self._register_emulator(emulator_name, config)

        container_name = f"emulator_{emulator_name}"
        try:
            existing_container = self.docker_client.containers.get(container_name)
            logger.info(f"Removing existing container {container_name}")
            try:
                existing_container.stop(timeout=10)
            except Exception as e:
                logger.warning(f"Failed to stop existing container: {e}")

            existing_container.remove()
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Error handling existing container: {e}")

        image_name = f"mobsec_emulator_{emulator_name}"
        ports = self._get_available_ports(emulator_name)

        emulator_path = config.get("path")
        dockerfile_path = os.path.join(emulator_path, "Dockerfile")

        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

        logger.info(f"Building Docker image for {emulator_name}...")
        self.docker_client.images.build(
            path=os.path.dirname(dockerfile_path),
            dockerfile=dockerfile_path,
            tag=image_name,
        )

        port_bindings = {}
        for service, external_port in ports.items():
            internal_port = self.base_ports[service]
            port_bindings[f"{internal_port}/tcp"] = external_port

        container = self.docker_client.containers.run(
            image_name,
            detach=True,
            privileged=True,
            network="mobsec_app_network",
            ports=port_bindings,
            environment={"REDIS_URL": self.redis_url, "EMULATOR_NAME": emulator_name},
            volumes={"mobsec_shared_data": {"bind": "/shared_data", "mode": "rw"}},
            name=container_name,
        )

        await self._update_emulator_status(emulator_name, "running", container.id)

        logger.info(f"Container started for {emulator_name}")
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
                    try:
                        container = self.docker_client.containers.get(
                            emulator.container_id
                        )
                        container.stop()
                        container.remove()
                        logger.info(f"Stopped emulator {emulator_name}")
                    except Exception as e:
                        logger.warning(f"Error stopping container: {e}")

                await self._update_emulator_status(emulator_name, "stopped", None)
                return True

        except Exception as e:
            logger.error(f"Error stopping emulator {emulator_name}: {e}")
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
        await self._create_emulator_table()

        async with self.async_session() as session:
            stmt = select(Emulator).where(Emulator.active == True)
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
            await self._create_emulator_table()

            for emulator_name, config in self.emulators_config.items():
                await self._register_emulator(emulator_name, config)

            active_emulators = [
                name
                for name, config in self.emulators_config.items()
                if config.get("active", False)
            ]

            if active_emulators:
                logger.info(f"Starting {len(active_emulators)} active emulators")
                started = 0
                for emulator_name in active_emulators:
                    try:
                        await self.start_emulator(emulator_name)
                        await self.connect_to_emulator(emulator_name)
                        started += 1
                    except Exception as e:
                        logger.error(f"Failed to start emulator {emulator_name}: {e}")

                logger.info(
                    f"Started {started}/{len(active_emulators)} emulators successfully"
                )
            else:
                logger.info("No active emulators configured")

        except Exception as e:
            logger.error(f"Error starting active emulators: {e}")

    async def connect_to_emulator(self, emulator_name: str) -> bool:
        """Connect to emulator via ADB"""
        status_data = await self.get_emulator_status(emulator_name)
        if "error" in status_data or status_data["status"] != "running":
            logger.warning(f"Emulator {emulator_name} is not running")
            return False

        container_id = status_data.get("container_id")
        if not container_id:
            logger.warning(f"No container ID for emulator {emulator_name}")
            return False

        container_ip = self._get_container_ip(container_id)
        if not container_ip:
            logger.warning(f"Could not get container IP for emulator {emulator_name}")
            return False

        logger.info(f"Connecting to emulator {emulator_name}...")
        connection_result = await self._adb_connect(container_ip, 5555)

        if connection_result:
            logger.info(f"Successfully connected to emulator {emulator_name}")
        else:
            logger.error(f"Failed to connect to emulator {emulator_name}")

        return connection_result
