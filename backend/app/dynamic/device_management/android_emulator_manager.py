import asyncio
import logging
import os
import subprocess
from typing import Any, Dict, Optional

from app.dynamic.device_management.base_emulator_manager import BaseEmulatorManager
from app.dynamic.device_management.device_manager import DOCKER_HOST_ALIAS
from app.dynamic.utils.adb_utils import get_adb_env, ensure_adb_server

logger = logging.getLogger(__name__)


class AndroidEmulatorManager(BaseEmulatorManager):
    """Manager for Android emulators"""

    @property
    def os_type(self) -> str:
        return "android"

    async def start_emulator(
        self, emulator_name: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Start Android emulator"""
        logger.info("Starting Android emulator %s...", emulator_name)

        emulator_path = config.get("path")
        dockerfile_path = os.path.join(emulator_path, "Dockerfile")

        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")

        container_name = f"emulator_{emulator_name}"
        image_name = f"mobsec_emulator_{emulator_name}"

        logger.info("Building Docker image for %s...", emulator_name)
        await self.docker_service.build_image(emulator_path, image_name)

        # Map ports and build bindings
        mapped_ports = self._get_mapped_ports(config, emulator_name)
        port_bindings = self._build_port_bindings(mapped_ports, config)
        mounts = self._build_mounts(config, emulator_name)

        # Ensure volume subpaths exist
        await self._ensure_all_volume_subpaths(config, emulator_name)

        logger.info(
            "Starting container for %s with port mapping: %s",
            emulator_name,
            mapped_ports,
        )

        container = await self.docker_service.run_container(
            image=image_name,
            name=container_name,
            privileged=True,
            network="mobsec_app_network",
            ports=port_bindings,
            environment={"REDIS_URL": self.redis_url, "EMULATOR_NAME": emulator_name},
            mounts=mounts,
        )

        logger.info("Container started for %s", emulator_name)

        return {
            "name": emulator_name,
            "status": "running",
            "container_id": container.id,
            "mapped_ports": mapped_ports,
        }

    async def connect_to_emulator(
        self,
        emulator_name: str,
        container_id: str,
        config: Dict[str, Any],
        mapped_ports: Optional[Dict[str, int]] = None,
    ) -> bool:
        """Connect to Android emulator via ADB"""
        logger.info("Connecting to Android emulator %s...", emulator_name)

        try:
            await ensure_adb_server()

            container_ip = await self._get_container_ip(container_id)
            if not container_ip:
                logger.warning(
                    "Could not get container IP for emulator %s", emulator_name
                )
                return False

            # Android emulators expose ADB on port 5555 internally
            connection_result = await self._adb_connect(container_ip, 5555)

            if not connection_result:
                logger.error("Failed to connect to Android emulator %s", emulator_name)
                return False

            adb_port = (mapped_ports or {}).get("adb")
            if adb_port:
                if not await self._adb_connect(DOCKER_HOST_ALIAS, adb_port):
                    logger.warning(
                        "Emulator %s: adb connect via %s:%s failed",
                        emulator_name,
                        DOCKER_HOST_ALIAS,
                        adb_port,
                    )

            logger.info("Successfully connected to Android emulator %s", emulator_name)
            return True

        except Exception as e:
            logger.error(
                "Error connecting to Android emulator %s: %s", emulator_name, e
            )
            return False

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
