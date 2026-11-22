import asyncio
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from docker.types import Mount
import yaml

from app.services.docker_service import DockerService

logger = logging.getLogger(__name__)


class BaseEmulatorManager(ABC):
    """Base class for OS-specific emulator managers"""

    def __init__(
        self, emulators_path: str, docker_service: DockerService, redis_url: str
    ):
        self.emulators_path = emulators_path
        self.docker_service = docker_service
        self.redis_url = redis_url

    @property
    @abstractmethod
    def os_type(self) -> str:
        """Return OS type identifier (e.g., 'android', 'aurora')"""
        pass

    @abstractmethod
    async def start_emulator(
        self, emulator_name: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Start emulator with given config"""
        pass

    @abstractmethod
    async def connect_to_emulator(
        self,
        emulator_name: str,
        container_id: str,
        config: Dict[str, Any],
        mapped_ports: Optional[Dict[str, int]] = None,
    ) -> bool:
        """Connect to emulator after start"""
        pass

    def _find_available_port(
        self, start_range: int = 5000, end_range: int = 6000, exclude_ports: set = None
    ) -> int:
        """Find available port in given range, excluding already allocated ports"""
        import socket

        if exclude_ports is None:
            exclude_ports = set()

        for port in range(start_range, end_range):
            if port in exclude_ports:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.bind(("0.0.0.0", port))
                    return port
            except OSError:
                continue

        raise RuntimeError(
            f"Could not find available port in range {start_range}-{end_range}"
        )

    def _get_mapped_ports(
        self, config: Dict[str, Any], emulator_name: str
    ) -> Dict[str, int]:
        """Map internal ports to external available ports"""
        ports = config.get("ports", {})
        mapped_ports = {}
        allocated_ports = set()

        for port_name, internal_port in ports.items():
            external_port = self._find_available_port(exclude_ports=allocated_ports)
            mapped_ports[port_name] = external_port
            allocated_ports.add(external_port)
            logger.info(
                f"Mapped {emulator_name} port {port_name}: {internal_port} -> {external_port}"
            )

        return mapped_ports

    def _build_port_bindings(
        self, mapped_ports: Dict[str, int], config: Dict[str, Any]
    ) -> Dict[str, int]:
        """Build port bindings for Docker (internal:external mapping)"""
        internal_ports = config.get("ports", {})
        port_bindings = {}

        for port_name, external_port in mapped_ports.items():
            internal_port = internal_ports.get(port_name)
            if internal_port:
                # Docker format: internal_port/tcp -> external_port
                port_bindings[f"{internal_port}/tcp"] = external_port

        return port_bindings

    def _build_mounts(self, config: Dict[str, Any], emulator_name: str) -> List[Mount]:
        """Build Docker mounts from config volumes"""
        mounts = []
        volumes = config.get("volumes", [])

        for volume in volumes:
            mount = Mount(
                target=volume.get("target"),
                source=volume.get("source"),
                type="volume",
                subpath=volume.get("subpath"),
            )
            mounts.append(mount)

        return mounts

    async def _ensure_volume_subpath(self, volume_name: str, subpath: str) -> None:
        """Ensure a subdirectory exists inside a named volume"""
        await self.docker_service.run_container(
            image="busybox",
            name=f"mobsec_volume_init_{subpath}",
            command=["mkdir", "-p", f"/vol/{subpath}"],
            volumes={volume_name: {"bind": "/vol", "mode": "rw"}},
            remove=True,
            detach=False,
        )

    async def _ensure_all_volume_subpaths(
        self, config: Dict[str, Any], emulator_name: str
    ) -> None:
        """Ensure all volume subpaths exist"""
        volumes = config.get("volumes", [])
        for volume in volumes:
            source = volume.get("source")
            subpath = volume.get("subpath")
            if source and subpath:
                await self._ensure_volume_subpath(source, subpath)

    async def _get_container_ip(self, container_id: str) -> Optional[str]:
        """Get container IP address"""
        return await self.docker_service.get_container_ip(
            container_id, network_name="mobsec_app_network"
        )
