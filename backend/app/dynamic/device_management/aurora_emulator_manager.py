import asyncio
import logging
import os
import subprocess
from typing import Any, Dict, Optional

from app.dynamic.device_management.base_emulator_manager import BaseEmulatorManager

logger = logging.getLogger(__name__)


class AuroraEmulatorManager(BaseEmulatorManager):
    """Manager for Aurora OS emulators"""

    @property
    def os_type(self) -> str:
        return "aurora"

    async def start_emulator(
        self, emulator_name: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Start Aurora OS emulator"""
        logger.info("Starting Aurora OS emulator %s...", emulator_name)

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
        """Connect to Aurora OS emulator via SSH (no-op, connection happens on-demand)"""
        logger.info("Aurora OS emulator %s ready (SSH on demand)", emulator_name)
        return True
