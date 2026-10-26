import asyncio
import logging
import os
import threading

import docker
import docker.errors
from docker.models.containers import Container

logger = logging.getLogger(__name__)


class DockerService:
    _instance: "DockerService" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.docker_client = docker.from_env()
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "DockerService":
        return cls()

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        if kwargs:
            return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
        return await loop.run_in_executor(None, func, *args)

    async def build_image(self, path: str, tag: str) -> None:
        dockerfile_path = os.path.join(path, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"No Dockerfile found in {path}")

        logger.info("Building Docker image %s from %s...", tag, dockerfile_path)
        try:
            await self._run_sync(self.docker_client.images.build, path=path, tag=tag)
            logger.info("Successfully built image %s", tag)
        except docker.errors.APIError as e:
            logger.error("Failed to build image %s: %s", tag, e)
            raise

    async def run_container(self, image: str, name: str, **kwargs) -> Container:
        await self._remove_existing_container(name)

        kwargs.setdefault("detach", True)
        try:
            container = await self._run_sync(
                self.docker_client.containers.run, image, name=name, **kwargs
            )
        except docker.errors.APIError as e:
            logger.error("Failed to start container %s (%s): %s", name, image, e)
            raise

        return container

    async def _remove_existing_container(self, name: str) -> None:
        existing_container = await self.get_container(name)
        if existing_container is None:
            return

        logger.info("Removing existing container %s", name)
        try:
            await self._run_sync(existing_container.stop, timeout=10)
        except docker.errors.APIError as exc:
            logger.warning("Failed to stop existing container %s: %s", name, exc)

        try:
            await self._run_sync(existing_container.remove, force=True)
        except docker.errors.APIError as exc:
            logger.warning("Failed to remove existing container %s: %s", name, exc)

    async def stop_container(self, name_or_id: str, timeout: int = 10) -> None:
        container = await self.get_container(name_or_id)
        if container is None:
            return

        try:
            await self._run_sync(container.stop, timeout=timeout)
        except docker.errors.APIError as exc:
            logger.warning("Failed to stop container %s: %s", name_or_id, exc)

        await self.remove_container(name_or_id, force=True)

    async def remove_container(self, name_or_id: str, force: bool = True) -> None:
        container = await self.get_container(name_or_id)
        if container is None:
            return
        try:
            await self._run_sync(container.remove, force=force)
        except docker.errors.APIError as exc:
            logger.warning("Failed to remove container %s: %s", name_or_id, exc)

    async def get_container(self, name_or_id: str) -> Container | None:
        try:
            return await self._run_sync(self.docker_client.containers.get, name_or_id)
        except docker.errors.NotFound:
            return None
        except docker.errors.APIError as exc:
            logger.warning("Error fetching container %s: %s", name_or_id, exc)
            return None

    async def list_containers(self, name_prefix: str | None = None) -> list[Container]:
        filters = {"name": f"^{name_prefix}"} if name_prefix else {}
        try:
            return await self._run_sync(
                self.docker_client.containers.list, all=True, filters=filters
            )
        except docker.errors.APIError as e:
            logger.error("Error listing containers: %s", e)
            return []

    async def get_container_ip(
        self, container_id: str, network_name: str
    ) -> str | None:
        container = await self.get_container(container_id)
        if container is None:
            logger.warning("Container %s not found while resolving IP", container_id)
            return None

        try:
            networks = container.attrs["NetworkSettings"]["Networks"]
        except (KeyError, TypeError) as e:
            logger.error("Unexpected container attrs for %s: %s", container_id, e)
            return None

        if network_name in networks:
            return networks[network_name]["IPAddress"]

        for network in networks.values():
            if network.get("IPAddress"):
                return network["IPAddress"]

        return None

    async def cleanup_by_prefix(self, prefix: str) -> None:
        containers = await self.list_containers(prefix)

        container_tasks = [self._run_sync(c.remove, force=True) for c in containers]
        if container_tasks:
            results = await asyncio.gather(*container_tasks, return_exceptions=True)
            for container, result in zip(containers, results):
                if isinstance(result, Exception):
                    logger.warning(
                        "Failed to remove container %s: %s", container.name, result
                    )

        images = await self._run_sync(self.docker_client.images.list)
        targets = [
            image
            for image in images
            if any(tag.startswith(f"{prefix}") for tag in image.tags)
        ]
        image_tasks = [
            self._run_sync(self.docker_client.images.remove, image.id, force=True)
            for image in targets
        ]
        if image_tasks:
            results = await asyncio.gather(*image_tasks, return_exceptions=True)
            for image, result in zip(targets, results):
                if isinstance(result, Exception):
                    logger.warning("Failed to remove image %s: %s", image.id, result)

        logger.info("Cleanup complete.")
