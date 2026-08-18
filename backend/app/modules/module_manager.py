import asyncio
import json
import logging
import os
import threading
import uuid
from typing import Any, Dict, Optional

import docker
import yaml
from redis import Redis
from sqlalchemy.future import select

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from urllib.parse import urlencode

from app.core.database_manager import db_manager
from app.models.app import ScanStatus
from app.models.module import Module, ModuleType

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ModuleManager:
    _instance: "ModuleManager" = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, redis_url: str, modules_path: str):
        if getattr(self, "_initialized", False):
            return

        if not redis_url or not modules_path:
            raise ValueError("ModuleManager requires redis_url and modules_path")

        self.redis_url = redis_url
        self.modules_path = modules_path
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.docker_client = docker.from_env()
        self.modules_config = self._load_modules_config()
        self.async_session = db_manager.session_factory
        self._initialized = True
        self.module_name_mappings = {}

    @classmethod
    def get_instance(
        cls, redis_url: Optional[str] = None, modules_path: Optional[str] = None
    ) -> "ModuleManager":
        if cls._instance is None:
            if redis_url is None or modules_path is None:
                raise ValueError(
                    "ModuleManager.get_instance requires redis_url and modules_path on first call"
                )
            cls(redis_url=redis_url, modules_path=modules_path)
        return cls._instance

    def _load_modules_config(self) -> Dict[str, Any]:
        """Load configuration for all modules"""
        configs = {}
        try:
            for module_name in os.listdir(self.modules_path):
                config_path = os.path.join(
                    self.modules_path, module_name, "config.yaml"
                )
                if os.path.exists(config_path):
                    with open(config_path, encoding="utf-8") as f:
                        config = yaml.safe_load(f)
                        configs[module_name] = config
        except Exception as e:
            logger.error("Error loading module configs: %s", str(e))
        return configs

    async def _register_module(self, module_name: str, config: dict):
        """
        Register a new module or update existing one in the database.

        Args:
            module_name (str): Name of the module
            config (dict): Module configuration containing:
                - version: str or float
                - description: str
                - config: dict

        Returns:
            dict: Created or updated module data
        """
        async with self.async_session() as session:
            # Check if module already exists
            stmt = select(Module).where(Module.name == module_name)
            result = await session.execute(stmt)
            existing_module = result.scalar_one_or_none()

            # Convert version to string if it exists
            version = config.get("version")
            if version is not None:
                version = str(version)

            module_type = (
                ModuleType.DYNAMIC
                if config.get("type") == "dynamic"
                else ModuleType.STATIC
            )

            if config.get("map_name", None) != None:
                map_name = config.get("map_name")
                self.module_name_mappings[map_name] = module_name

            if existing_module:
                existing_module.version = version
                existing_module.description = config.get("description")
                existing_module.config = config.get("config", {})
                existing_module.module_type = module_type
                module = existing_module
            else:
                module = Module(
                    name=module_name,
                    version=version,
                    description=config.get("description"),
                    config=config.get("config", {}),
                    module_type=module_type,
                )
                session.add(module)

            await session.commit()
            await session.refresh(module)

            return {
                "name": module.name,
                "version": module.version,
                "description": module.description,
                "config": module.config,
            }

    async def _build_image_async(self, image_name: str, module_path: str) -> None:
        """Build Docker image asynchronously"""
        dockerfile_path = os.path.join(module_path, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"No Dockerfile found in {module_path}")

        logger.info("Building Docker image %s from %s...", image_name, dockerfile_path)
        try:
            # Run docker build in a thread pool to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.docker_client.images.build(
                    path=module_path, tag=image_name
                ),
            )
            logger.info("Successfully built image %s", image_name)
        except Exception as e:
            logger.error("Failed to build image %s: %s", image_name, str(e))
            raise

    async def _start_container_async(self, module_name: str, image_name: str) -> None:
        """Start Docker container asynchronously"""
        logger.info("Starting module: %s", module_name)
        module_config = self.modules_config.get(module_name, {})
        is_dynamic = module_config.get("type") == "dynamic"

        try:
            run_kwargs = {
                "image": image_name,
                "detach": True,
                "environment": {
                    "REDIS_URL": self.redis_url,
                    "MODULE_NAME": module_name,
                },
                "volumes": {
                    "mobsec_shared_data": {"bind": "/shared_data", "mode": "rw"}
                },
                "name": image_name,
            }

            if is_dynamic:
                run_kwargs["network"] = "mobsec_app_network"
                run_kwargs["environment"]["DATABASE_URL"] = os.getenv(
                    "DATABASE_URL", ""
                )
                run_kwargs["environment"]["PORT"] = str(module_config.get("port", 8090))
            else:
                run_kwargs["network"] = "mobsec_app_network"

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.run(**run_kwargs),
            )
            logger.info("Successfully started container %s", image_name)
        except Exception as e:
            logger.error("Failed to start container %s: %s", image_name, str(e))
            raise

    def _image_name(self, module_name: str) -> str:
        return f"mobsec_{module_name}"

    async def _get_container(self, module_name: str):
        """Fetch a module's container, or None if it doesn't exist."""
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(
                None, self.docker_client.containers.get, self._image_name(module_name)
            )
        except docker.errors.NotFound:
            return None

    async def start_module(self, module_name: str) -> None:
        """Start a single module asynchronously"""
        image_name = self._image_name(module_name)
        module_path = os.path.join(self.modules_path, module_name)

        try:
            existing_container = await self._get_container(module_name)
            if existing_container is not None:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: existing_container.remove(force=True)
                )
                logger.info("Removed existing container: %s", image_name)

            await self._build_image_async(image_name, module_path)
            await self._start_container_async(module_name, image_name)
            await self._register_module(module_name, self.modules_config[module_name])

        except Exception as e:
            logger.error("Failed to start module %s: %s", module_name, str(e))
            raise

    async def start_modules(self) -> None:
        """Start all modules concurrently"""
        module_dirs = []
        for d in os.listdir(self.modules_path):
            if os.path.isdir(os.path.join(self.modules_path, d)):
                # Check if module is active in config
                module_config = self.modules_config.get(d, {})
                active_value = module_config.get("active", True)
                is_active = (
                    active_value
                    if isinstance(active_value, bool)
                    else str(active_value).strip().lower() == "true"
                )
                if is_active:
                    module_dirs.append(d)
                else:
                    logger.info("Skipping inactive module: %s", d)

        # Start all active modules concurrently
        tasks = [self.start_module(module_name) for module_name in module_dirs]

        # Wait for all modules to start, but continue if some fail
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Log any failures
        for module_name, result in zip(module_dirs, results):
            if isinstance(result, Exception):
                logger.error("Module %s failed to start: %s", module_name, str(result))

        # Relink chain modules after all modules are started
        from app.modules.chain_manager import ChainManager

        chain_manager = ChainManager.get_instance()
        await chain_manager.relink_chain_modules()

    async def stop_module(self, module_name: str):
        """Stop a single module asynchronously"""
        container = await self._get_container(module_name)
        if container is None:
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: container.stop(timeout=2))
        await loop.run_in_executor(None, lambda: container.remove(force=True))

    async def submit_task(
        self,
        module_name: str,
        data: Dict[str, Any],
        file_hash: str,
        chain_task_id: Optional[str] = None,
    ) -> str:
        """Submit a task to a module"""
        try:
            task_id = str(uuid.uuid4())

            # Prepare task data
            task_data = {
                "task_id": task_id,
                "file_hash": file_hash,
                "file_name": data.get("file_name", ""),
                "file_type": data.get("file_type", "unknown"),
                "folder_path": data.get("folder_path", ""),
                "chain_task_id": chain_task_id,
                "module_name": module_name,
            }

            # Store task data in Redis
            self.redis.set(f"task:{task_id}", json.dumps(task_data), ex=3600)

            # Add task to module's queue
            self.redis.rpush(f"module:{module_name}:queue", task_id)
            logger.info("Submitted task %s to module %s", task_id, module_name)

            # Import here to avoid circular imports
            from app.core.app_manager import storage

            await storage.update_scan_status(
                file_hash=file_hash, status=ScanStatus.SCANNING
            )

            return task_id

        except Exception as e:
            logger.error("Error submitting task to module %s: %s", module_name, str(e))
            return None

    async def cleanup(self):
        async with self.async_session() as session:
            # Get all active modules
            result = await session.execute(select(Module.name))
            active_modules = [row[0] for row in result.all()]

            # Stop and remove modules concurrently
            stop_tasks = [
                self.stop_module(module_name) for module_name in active_modules
            ]
            await asyncio.gather(*stop_tasks, return_exceptions=True)

            # Remove all containers and images asynchronously
            loop = asyncio.get_event_loop()

            # Get all containers
            containers = await loop.run_in_executor(
                None, lambda: self.docker_client.containers.list(all=True)
            )

            # Remove containers concurrently
            container_tasks = []
            for container in containers:
                if container.name.startswith("mobsec_"):
                    container_tasks.append(
                        loop.run_in_executor(
                            None, lambda c=container: c.remove(force=True)
                        )
                    )
            if container_tasks:
                await asyncio.gather(*container_tasks, return_exceptions=True)

            # Get all images
            images = await loop.run_in_executor(None, self.docker_client.images.list)

            # Remove images concurrently
            image_tasks = []
            for image in images:
                if any(tag.startswith("mobsec_") for tag in image.tags):
                    image_tasks.append(
                        loop.run_in_executor(
                            None,
                            lambda i=image: self.docker_client.images.remove(
                                i.id, force=True
                            ),
                        )
                    )
            if image_tasks:
                await asyncio.gather(*image_tasks, return_exceptions=True)

            logger.info("Cleanup complete.")

    async def check_module_exists(self, module_name: str) -> bool:
        """
        Check if a module exists and is active in the database.

        Args:
            module_name (str): Name of the module to check

        Returns:
            bool: True if the module exists, False otherwise
        """
        async with self.async_session() as session:
            stmt = select(Module).where(Module.name == module_name)
            result = await session.execute(stmt)
            module = result.scalar_one_or_none()
            return module is not None

    async def _get_running_container_names(self) -> set:
        loop = asyncio.get_event_loop()
        try:
            containers = await loop.run_in_executor(
                None, self.docker_client.containers.list
            )
            return {c.name for c in containers}
        except Exception as e:
            logger.error("Error listing running containers: %s", str(e))
            return set()

    async def list_modules(self, module_type: str | None = None):
        running_names = await self._get_running_container_names()

        modules_info = []
        for module_name, module_config in self.modules_config.items():
            if (
                module_type is not None
                and module_config.get("type", "static") != module_type
            ):
                continue

            module_info = {
                "id": module_config.get("id", module_name),
                "name": module_config.get("display_name", module_name),
                "description": module_config.get(
                    "description", "No description available"
                ),
                "active": self._image_name(module_name) in running_names,
                "is_external": False,
                "version": module_config.get("version", "0.1"),
                "input_formats": module_config.get("input_formats", ["apk"]),
                "module_type": module_config.get("type"),
            }

            if "map_name" in module_config:
                module_info["map_name"] = module_config.get("map_name")

            if (
                module_config.get("type") == ModuleType.DYNAMIC
                and "view" in module_config
            ):
                module_info["view"] = module_config.get("view")

            modules_info.append(module_info)

        return modules_info

    def get_module_ws_url(
        self, module_name: str, device_id: str, query_params: dict = None
    ) -> str:
        module_config = self.modules_config.get(module_name)

        if not module_config:
            raise ValueError(f"Module {module_name} not found")

        port = module_config.get("port")

        if not port:
            raise ValueError(f"Port not configured for module {module_name}")

        query_string = ""
        if query_params:
            query_string = f"?{urlencode(query_params)}"

        return f"ws://mobsec_{module_name}:{port}/ws/{device_id}{query_string}"

    async def proxy_websocket(
        self,
        websocket: WebSocket,
        module_name: str,
        device_id: str,
        query_params: dict = None,
    ) -> None:
        """Proxy a client WebSocket connection to a module WebSocket endpoint."""
        module_url = self.get_module_ws_url(module_name, device_id, query_params)
        await websocket.accept()
        logger.info("Proxying WebSocket for device %s to %s", device_id, module_url)

        try:
            async with websockets.connect(module_url) as module_ws:

                async def forward_to_module():
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if message["type"] == "websocket.receive":
                            if "text" in message:
                                await module_ws.send(message["text"])
                            elif "bytes" in message:
                                await module_ws.send(message["bytes"])

                async def forward_to_client():
                    async for data in module_ws:
                        if isinstance(data, str):
                            await websocket.send_text(data)
                        else:
                            await websocket.send_bytes(data)

                forward_tasks = [
                    asyncio.create_task(forward_to_module()),
                    asyncio.create_task(forward_to_client()),
                ]
                done, pending = await asyncio.wait(
                    forward_tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                for task in done:
                    if task.exception():
                        raise task.exception()
        except WebSocketDisconnect:
            logger.info("Client WebSocket disconnected for device %s", device_id)
        except Exception as e:
            logger.error("WebSocket proxy error for %s: %s", module_name, str(e))
            try:
                await websocket.close(code=4000, reason=str(e))
            except Exception:
                pass
