import os
import json
import yaml
import docker
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from app.models.chain import Module
from redis import Redis
from app.core.app_manager import storage
from app.models.app import ScanStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ModuleManager:
    def __init__(self, redis_url: str, modules_path: str):
        self.redis_url = redis_url
        self.modules_path = modules_path
        self.redis = Redis.from_url(redis_url, decode_responses=True)
        self.docker_client = docker.from_env()
        self.modules_config = self._load_modules_config()

        database_url = os.getenv('DATABASE_URL', 'postgresql+asyncpg://postgres:password@db:5432/mobsec_db')
        self.engine = create_async_engine(database_url)
        self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)

    def _load_modules_config(self) -> Dict[str, Any]:
        """Load configuration for all modules"""
        configs = {}
        try:
            for module_name in os.listdir(self.modules_path):
                config_path = os.path.join(self.modules_path, module_name, 'config.yaml')
                if os.path.exists(config_path):
                    with open(config_path) as f:
                        config = yaml.safe_load(f)
                        configs[module_name] = config
        except Exception as e:
            logger.error(f"Error loading module configs: {str(e)}")
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
            version = config.get('version')
            if version is not None:
                version = str(version)
            
            if existing_module:
                existing_module.version = version
                existing_module.description = config.get('description')
                existing_module.config = config.get('config', {})
                module = existing_module
            else:
                module = Module(
                    name=module_name,
                    version=version,
                    description=config.get('description'),
                    config=config.get('config', {})
                )
                session.add(module)
            
            await session.commit()
            await session.refresh(module)
            
            return {
                "name": module.name,
                "version": module.version,
                "description": module.description,
                "config": module.config
            }

    async def _build_image_async(self, image_name: str, module_path: str) -> None:
        """Build Docker image asynchronously"""
        dockerfile_path = os.path.join(module_path, "Dockerfile")
        if not os.path.exists(dockerfile_path):
            raise FileNotFoundError(f"No Dockerfile found in {module_path}")

        logger.info(f"Building Docker image {image_name} from {dockerfile_path}...")
        try:
            # Run docker build in a thread pool to not block
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.docker_client.images.build(path=module_path, tag=image_name)
            )
            logger.info(f"Successfully built image {image_name}")
        except Exception as e:
            logger.error(f"Failed to build image {image_name}: {str(e)}")
            raise

    async def _start_container_async(self, module_name: str, image_name: str) -> None:
        """Start Docker container asynchronously"""
        logger.info(f"Starting module: {module_name}")
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.run(
                    image_name,
                    detach=True,
                    network="mobsec_app_network",
                    environment={"REDIS_URL": self.redis_url, "MODULE_NAME": module_name},
                    volumes={'mobsec_shared_data': {'bind': '/shared_data', 'mode': 'rw'}},
                    name=image_name
                )
            )
            logger.info(f"Successfully started container {image_name}")
        except Exception as e:
            logger.error(f"Failed to start container {image_name}: {str(e)}")
            raise

    async def start_module(self, module_name: str) -> None:
        """Start a single module asynchronously"""
        image_name = f"mobsec_{module_name}"
        module_path = os.path.join(self.modules_path, module_name)
        
        try:
            try:
                existing_container = self.docker_client.containers.get(image_name)
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: existing_container.remove(force=True)
                )
                logger.info(f"Removed existing container: {image_name}")
            except docker.errors.NotFound:
                pass

            await self._build_image_async(image_name, module_path)
            await self._start_container_async(module_name, image_name)
            await self._register_module(module_name, self.modules_config[module_name])
            
        except Exception as e:
            logger.error(f"Failed to start module {module_name}: {str(e)}")
            raise

    async def start_modules(self) -> None:
        """Start all modules concurrently"""
        module_dirs = []
        for d in os.listdir(self.modules_path):
            if os.path.isdir(os.path.join(self.modules_path, d)):
                # Check if module is active in config
                module_config = self.modules_config.get(d, {})
                active_value = module_config.get('active', True)
                is_active = active_value if isinstance(active_value, bool) else str(active_value).strip().lower() == "true"
                if is_active:
                    module_dirs.append(d)
                else:
                    logger.info(f"Skipping inactive module: {d}")
        
        # Start all active modules concurrently
        tasks = [self.start_module(module_name) for module_name in module_dirs]
        
        # Wait for all modules to start, but continue if some fail
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log any failures
        for module_name, result in zip(module_dirs, results):
            if isinstance(result, Exception):
                logger.error(f"Module {module_name} failed to start: {str(result)}")
        
        # Relink chain modules after all modules are started
        from app.modules.chain_manager import ChainManager
        chain_manager = ChainManager()
        await chain_manager.relink_chain_modules()

    async def stop_module(self, module_name: str):
        """Stop a single module asynchronously"""
        try:
            loop = asyncio.get_event_loop()
            container = self.docker_client.containers.get(f"mobsec_{module_name}")
            await loop.run_in_executor(
                None,
                lambda: container.stop(timeout=2)
            )
            await loop.run_in_executor(
                None,
                lambda: container.remove(force=True)
            )
        except docker.errors.NotFound:
            pass

    async def submit_task(
        self, 
        module_name: str, 
        data: Dict[str, Any], 
        file_hash: str,
        chain_task_id: Optional[str] = None
    ) -> str:
        """Submit a task to a module"""
        try:
            task_id = str(uuid.uuid4())
            
            # Prepare task data
            task_data = {
                "task_id": task_id,
                "file_hash": file_hash,
                "file_name": data.get("file_name", ""),  # Changed from apk_name
                "file_type": data.get("file_type", "unknown"),  # Added file type
                "folder_path": data.get("folder_path", ""),
                "chain_task_id": chain_task_id,
                "module_name": module_name
            }
            
            # Store task data in Redis
            self.redis.set(
                f"task:{task_id}",
                json.dumps(task_data),
                ex=3600  # Expire after 1 hour
            )
            
            # Add task to module's queue
            self.redis.rpush(f"module:{module_name}:queue", task_id)
            logger.info(f"Submitted task {task_id} to module {module_name}")
            
            await storage.update_scan_status(
                file_hash=file_hash,
                status=ScanStatus.SCANNING
            )

            return task_id
            
        except Exception as e:
            logger.error(f"Error submitting task to module {module_name}: {str(e)}")
            return None


    async def cleanup(self):
        async with self.async_session() as session:
            # Get all active modules
            result = await session.execute(select(Module.name))
            active_modules = [row[0] for row in result.all()]

            # Stop and remove modules concurrently
            stop_tasks = [self.stop_module(module_name) for module_name in active_modules]
            await asyncio.gather(*stop_tasks, return_exceptions=True)

            # Remove all containers and images asynchronously
            loop = asyncio.get_event_loop()
            
            # Get all containers
            containers = await loop.run_in_executor(
                None,
                lambda: self.docker_client.containers.list(all=True)
            )
            
            # Remove containers concurrently
            container_tasks = []
            for container in containers:
                if container.name.startswith("mobsec_"):
                    container_tasks.append(
                        loop.run_in_executor(
                            None,
                            lambda c=container: c.remove(force=True)
                        )
                    )
            if container_tasks:
                await asyncio.gather(*container_tasks, return_exceptions=True)
            
            # Get all images
            images = await loop.run_in_executor(
                None,
                lambda: self.docker_client.images.list()
            )
            
            # Remove images concurrently
            image_tasks = []
            for image in images:
                if any(tag.startswith("mobsec_") for tag in image.tags):
                    image_tasks.append(
                        loop.run_in_executor(
                            None,
                            lambda i=image: self.docker_client.images.remove(i.id, force=True)
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

