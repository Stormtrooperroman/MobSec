import asyncio
import contextlib
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import yaml
from sqlalchemy.future import select

from app.models.chain import (
    Chain,
    ChainExecution,
    ChainStatus,
    ModuleExecution,
    chain_modules,
)
from app.core.database_manager import db_manager
from app.models.module import Module
from app.services.redis_service import RedisService

logger = logging.getLogger(__name__)


class ChainManager:
    _instance: "ChainManager" = None
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

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

        self.async_session = db_manager.session_factory
        self.redis_service = RedisService.get_instance(redis_url)

        # Runtime members initialised lazily
        self.chain_event_queue: Optional[asyncio.Queue] = None
        self._queue_worker_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._starting = False
        self._started = False

        # Store config for lazy initialization
        self.redis_url = redis_url
        self.modules_path = os.getenv("MODULES_PATH", "/app/modules")

        self._initialized = True

    @classmethod
    def get_instance(cls) -> "ChainManager":
        if cls._instance is None:
            cls()
        return cls._instance

    async def startup(self):
        if self._started:
            return

        while self._starting:
            await asyncio.sleep(0.05)
            if self._started:
                return

        self._starting = True
        try:
            if self.chain_event_queue is None:
                self.chain_event_queue = asyncio.Queue()

            if not self._monitor_task or self._monitor_task.done():
                self._monitor_task = asyncio.create_task(self._monitor_chain_events())

            if not self._queue_worker_task or self._queue_worker_task.done():
                self._queue_worker_task = asyncio.create_task(
                    self._process_chain_event_queue()
                )

            self._started = True
        finally:
            self._starting = False

    async def shutdown(self):
        for task in (self._monitor_task, self._queue_worker_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        self._monitor_task = None
        self._queue_worker_task = None
        self._started = False

    async def _handle_chain_event(self, chain_task_id, next_module_index, file_hash):
        """Handle a single chain event"""
        lock_acquired = await self.redis_service.acquire_chain_module_lock(
            chain_task_id, next_module_index
        )

        if not lock_acquired:
            logger.info(
                "Duplicate event for chain %s, module %s - skipping",
                chain_task_id,
                next_module_index,
            )
            return

        chain_data = await self.redis_service.get_chain_state(chain_task_id)
        if chain_data is None:
            logger.error(
                "Chain state missing for %s - cannot advance chain", chain_task_id
            )
            return

        modules = chain_data.get("modules", [])
        await self.redis_service.delete_chain_completed_key(chain_task_id)

        if next_module_index >= len(modules):
            await self._complete_chain(chain_task_id)
            return

        is_running = await self._is_module_already_running(
            chain_task_id, next_module_index
        )

        if is_running:
            logger.info(
                "Module %s for chain %s is already running, skipping",
                next_module_index,
                chain_task_id,
            )
        else:
            await self._start_module(chain_task_id, next_module_index, file_hash)

    async def _process_chain_event_queue(self):
        """Process chain events from the queue in the main event loop"""
        while True:
            try:
                if not self.chain_event_queue:
                    await asyncio.sleep(0.1)
                    continue
                event = await self.chain_event_queue.get()
                chain_task_id = event.get("chain_task_id")
                next_module_index = event.get("next_module_index")
                file_hash = event.get("file_hash")

                if chain_task_id and next_module_index is not None and file_hash:
                    await self._handle_chain_event(
                        chain_task_id, next_module_index, file_hash
                    )

                self.chain_event_queue.task_done()
            except Exception as e:
                logger.error("Error processing chain event from queue: %s", str(e))

    async def _is_module_already_running(self, chain_task_id, module_index):
        """Check if a module is already running by checking database"""
        async with self.async_session() as session:
            module_execution_id = f"{chain_task_id}_module_{module_index}"
            stmt = select(ModuleExecution).where(
                ModuleExecution.id == module_execution_id
            )
            result = await session.execute(stmt)
            module_execution = result.scalar_one_or_none()

            if module_execution and module_execution.status == ChainStatus.RUNNING:
                return True

            return False

    async def _monitor_chain_events(self):
        """Consume chain-completion events from Redis pub/sub."""
        logger.info("Starting Redis chain event monitor")
        try:
            async for data in self.redis_service.listen_chain_events():
                if self.chain_event_queue is not None:
                    await self.chain_event_queue.put(data)
        except asyncio.CancelledError:
            logger.info("Chain event monitor stopped")
            raise
        except Exception as e:
            logger.error("Chain event monitor failed: %s", str(e))

    async def init_db(self):
        from app.core.settings_db import init_db

        await init_db()

    async def get_chain_by_name(self, chain_name: str):
        async with self.async_session() as session:
            stmt = select(Chain).where(Chain.name == chain_name)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if chain:
                modules_stmt = (
                    select(Module, chain_modules.c.order, chain_modules.c.parameters)
                    .join(chain_modules, Module.name == chain_modules.c.module_name)
                    .where(chain_modules.c.chain_name == chain_name)
                    .order_by(chain_modules.c.order)
                )

                modules_result = await session.execute(modules_stmt)

                chain_modules_list = [
                    {
                        "module": {
                            "name": module.name,
                            "version": module.version,
                            "description": module.description,
                            "config": module.config,
                        },
                        "order": order,
                        "parameters": parameters,
                    }
                    for module, order, parameters in modules_result
                ]

                chain_dict = {
                    "name": chain.name,
                    "description": chain.description,
                    "created_at": chain.created_at,
                    "updated_at": chain.updated_at,
                    "modules": chain_modules_list,
                }
                return chain_dict
            return None

    async def get_all_chains(self):
        async with self.async_session() as session:
            stmt = (
                select(
                    Chain.name,
                    Chain.description,
                    Chain.created_at,
                    Chain.updated_at,
                    Module.name.label("module_name"),
                    Module.version.label("module_version"),
                    Module.description.label("module_description"),
                    Module.config.label("module_config"),
                    chain_modules.c.order,
                    chain_modules.c.parameters,
                )
                .select_from(Chain)
                .join(chain_modules, Chain.name == chain_modules.c.chain_name)
                .join(Module, Module.name == chain_modules.c.module_name)
                .order_by(Chain.name, chain_modules.c.order)
            )

            result = await session.execute(stmt)
            rows = result.all()

            chains_dict = {}
            for row in rows:
                chain_name = row.name
                if chain_name not in chains_dict:
                    chains_dict[chain_name] = {
                        "name": row.name,
                        "description": row.description,
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                        "modules": [],
                    }

                chains_dict[chain_name]["modules"].append(
                    {
                        "module": {
                            "name": row.module_name,
                            "version": row.module_version,
                            "description": row.module_description,
                            "config": row.module_config,
                        },
                        "order": row.order,
                        "parameters": row.parameters,
                    }
                )

            return list(chains_dict.values())

    async def update_chain(self, chain_name: str, new_data: dict):
        async with self.async_session() as session:
            stmt = select(Chain).where(Chain.name == chain_name)
            result = await session.execute(stmt)
            chain = result.scalar_one_or_none()

            if not chain:
                return None

            if "description" in new_data:
                chain.description = new_data["description"]

            if "modules" in new_data:
                await session.execute(
                    chain_modules.delete().where(
                        chain_modules.c.chain_name == chain_name
                    )
                )

                for module_config in new_data["modules"]:
                    module_stmt = select(Module).where(
                        Module.name == module_config["name"]
                    )
                    module = await session.execute(module_stmt)
                    module = module.scalar_one_or_none()

                    if not module:
                        raise ValueError(
                            f"Module with name {module_config['name']} not found"
                        )

                    stmt = chain_modules.insert().values(
                        chain_name=chain_name,
                        module_name=module_config["name"],
                        order=module_config["order"],
                        parameters=module_config.get("parameters", {}),
                    )
                    await session.execute(stmt)

            await session.commit()

            return await self.get_chain_by_name(chain_name)

    async def create_chain(self, chain_data: dict):
        async with self.async_session() as session:
            new_chain = Chain(
                name=chain_data["name"], description=chain_data.get("description")
            )
            session.add(new_chain)

            if "modules" in chain_data:
                for module_config in chain_data["modules"]:
                    module = await session.execute(
                        select(Module).where(Module.name == module_config["name"])
                    )
                    module = module.scalar_one_or_none()

                    if not module:
                        raise ValueError(
                            f"Module with name {module_config['name']} not found"
                        )

                    stmt = chain_modules.insert().values(
                        chain_name=new_chain.name,
                        module_name=module.name,
                        order=module_config["order"],
                        parameters=module_config.get("parameters", {}),
                    )
                    await session.execute(stmt)

            await session.commit()
            await session.refresh(new_chain)

            return new_chain

    async def delete_chain(self, chain_name: str):
        async with self.async_session() as session:
            await session.execute(
                chain_modules.delete().where(chain_modules.c.chain_name == chain_name)
            )

            result = await session.execute(
                select(Chain).where(Chain.name == chain_name)
            )
            chain = result.scalar_one_or_none()

            if not chain:
                return False

            await session.delete(chain)
            await session.commit()
            return True

    async def run_chain(self, chain_name: str, file_hash: str):
        """
        Run a chain analysis on a file

        Args:
            chain_name: Name of the chain to run
            file_hash: Hash of the file to analyze

        Returns:
            dict: Task information
        """
        chain = await self.get_chain_by_name(chain_name)
        if not chain:
            raise ValueError(f"Chain '{chain_name}' not found")

        from app.core.app_manager import storage

        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            raise ValueError(f"File with hash '{file_hash}' not found")

        folder = file_info.get("folder_path", "")
        if not folder:
            original_name = file_info.get("original_name", "unknown")
            folder = "_".join(original_name.split(".")[0].split()) + "-" + file_hash

        task_id = f"chain_{uuid.uuid4()}"

        modules = chain.get("modules", [])
        if not modules:
            raise ValueError(f"Chain '{chain_name}' has no modules defined")

        async with self.async_session() as session:
            chain_execution = ChainExecution(
                id=task_id,
                chain_name=chain_name,
                status=ChainStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
            )
            session.add(chain_execution)

            for idx, module_config in enumerate(modules):
                module_name = module_config["module"]["name"]
                module_execution = ModuleExecution(
                    id=f"{task_id}_module_{idx}",
                    chain_execution_id=task_id,
                    module_name=module_name,
                    order=idx,
                    status=ChainStatus.PENDING,
                    parameters=module_config.get("parameters", {}),
                )
                session.add(module_execution)

            await session.commit()

        await self.redis_service.set_chain_state(
            task_id,
            {
                "chain_name": chain_name,
                "file_hash": file_hash,
                "modules": [m["module"]["name"] for m in modules],
                "current_index": 0,
                "results": {},
                "file_type": file_info.get("file_type", "unknown"),
                "folder_path": folder,
                "file_name": file_info.get("original_name", ""),
            },
        )

        await self._start_module(task_id, 0, file_hash)

        return {
            "status": "success",
            "message": f"Chain '{chain_name}' execution started for file {file_hash}",
            "task_id": task_id,
        }

    async def _start_module(self, chain_task_id, module_index, file_hash):
        """Start execution of a specific module in the chain"""
        module_task_id = None
        try:
            chain_data = await self.redis_service.get_chain_state(chain_task_id)
            if not chain_data:
                raise ValueError(f"Chain data not found for task {chain_task_id}")

            data = {
                "folder_path": chain_data["folder_path"],
                "file_name": chain_data["file_name"],
                "file_type": chain_data["file_type"],
                "created_at": datetime.now(timezone.utc).timestamp(),
            }

            module_name = chain_data["modules"][module_index]

            if module_name.startswith("external:"):
                # This part is for future updates and doesn't work yet
                pass
            else:
                # Import here to avoid circular imports
                from app.modules.module_manager import ModuleManager

                module_manager = ModuleManager.get_instance(
                    redis_url=self.redis_url, modules_path=self.modules_path
                )
                module_task_id = await module_manager.submit_task(
                    module_name=module_name,
                    data=data,
                    file_hash=file_hash,
                    chain_task_id=chain_task_id,
                )

                if not module_task_id:
                    raise ValueError(f"Failed to submit task to module {module_name}")

                async with self.async_session() as session:
                    module_execution_id = f"{chain_task_id}_module_{module_index}"
                    stmt = select(ModuleExecution).where(
                        ModuleExecution.id == module_execution_id
                    )
                    result = await session.execute(stmt)
                    module_execution = result.scalar_one_or_none()

                    if module_execution:
                        module_execution.status = ChainStatus.RUNNING
                        module_execution.started_at = datetime.now(timezone.utc)
                        module_execution.task_id = module_task_id
                        await session.commit()

                logger.info(
                    "Started module %s for chain %s", module_name, chain_task_id
                )

        except Exception as e:
            logger.error("Error starting module: %s", str(e))
            await self._fail_module(chain_task_id, module_index, str(e))

            if module_task_id:
                await self.redis_service.delete_task(module_task_id)

    async def _cleanup_chain_redis_state(self, chain_task_id):
        chain_data = await self.redis_service.get_chain_state(chain_task_id)
        file_hash = chain_data.get("file_hash") if chain_data else None
        if chain_data and file_hash:
            for module_name in chain_data.get("modules", []):
                await self.redis_service.delete_result(module_name, file_hash)
                await self.redis_service.delete_tasks_for(
                    file_hash, module_name=module_name
                )

        await self.redis_service.delete_chain_keys(chain_task_id)

    async def _complete_chain(self, chain_task_id):
        """Mark chain as completed"""
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(ChainExecution).where(ChainExecution.id == chain_task_id)
                )

                chain_execution = result.scalar_one_or_none()
                if chain_execution:
                    chain_execution.status = ChainStatus.COMPLETED
                    chain_execution.completed_at = datetime.now(timezone.utc)
                    await session.commit()

            await self._cleanup_chain_redis_state(chain_task_id)

            logger.info("Chain %s completed successfully", chain_task_id)
        except Exception as e:
            logger.error("Error completing chain %s: %s", chain_task_id, str(e))

    async def _fail_chain(self, chain_task_id, error_message):
        """Mark chain as failed"""
        try:
            async with self.async_session() as session:
                result = await session.execute(
                    select(ChainExecution).where(ChainExecution.id == chain_task_id)
                )

                chain_execution = result.scalar_one_or_none()
                if chain_execution:
                    chain_execution.status = ChainStatus.FAILED
                    chain_execution.completed_at = datetime.now(timezone.utc)
                    chain_execution.error_message = error_message
                    await session.commit()

            await self._cleanup_chain_redis_state(chain_task_id)

            logger.error("Chain %s failed: %s", chain_task_id, error_message)
        except Exception as e:
            logger.error("Error failing chain %s: %s", chain_task_id, str(e))

    async def _fail_module(self, chain_task_id, module_index, error_message):
        """Mark module as failed"""
        async with self.async_session() as session:
            module_execution_id = f"{chain_task_id}_module_{module_index}"
            module_execution = (
                await session.execute(
                    select(ModuleExecution).where(
                        ModuleExecution.id == module_execution_id
                    )
                )
            ).scalar_one_or_none()

            if module_execution:
                module_execution.status = ChainStatus.FAILED
                module_execution.completed_at = datetime.now(timezone.utc)
                module_execution.error_message = error_message
                await session.commit()

    async def relink_chain_modules(self):
        """Relink existing chains with their modules after system restart"""
        async with self.async_session() as session:
            await session.execute(chain_modules.delete())

            chains_stmt = select(Chain)
            chains_result = await session.execute(chains_stmt)
            chains = chains_result.scalars().all()

            for chain in chains:
                modules_stmt = select(Module)
                modules_result = await session.execute(modules_stmt)
                available_modules = {m.name: m for m in modules_result.scalars().all()}

                chain_data = await self.get_chain_by_name(chain.name)
                logger.info("Relinking chain %s with modules", chain.name)

                if chain_data and chain_data.get("modules"):
                    for module_config in chain_data["modules"]:
                        module_name = module_config["module"]["name"]

                        if module_name in available_modules:
                            try:
                                stmt = chain_modules.insert().values(
                                    chain_name=chain.name,
                                    module_name=module_name,
                                    order=module_config.get("order", 0),
                                    parameters=module_config.get("parameters", {}),
                                )
                                await session.execute(stmt)
                                logger.info(
                                    "Relinked module %s to chain %s",
                                    module_name,
                                    chain.name,
                                )
                            except Exception as e:
                                logger.error(
                                    "Failed to relink module %s to chain %s: %s",
                                    module_name,
                                    chain.name,
                                    str(e),
                                )
                        else:
                            logger.warning(
                                "Module %s not found for chain %s",
                                module_name,
                                chain.name,
                            )

            await session.commit()
            logger.info("Chain module relinking completed")

    async def create_default_chains(self):
        """Create default chains from YAML files in root modules folder"""
        modules_path = os.getenv("MODULES_PATH", "./app/modules")
        logger.info("Looking for chain definitions in: %s", modules_path)

        try:
            files = os.listdir(modules_path)
            logger.info("Found files in directory: %s", files)

            for file_name in files:
                if file_name.endswith(".yaml") and not file_name == "config.yaml":
                    yaml_path = os.path.join(modules_path, file_name)
                    logger.info("Processing chain file: %s", yaml_path)
                    await self._process_chain_yaml(yaml_path)

        except Exception as e:
            logger.error("Error processing chain definitions: %s", str(e))

    async def _process_chain_yaml(self, yaml_path: str):
        """Process a YAML file containing chain definitions"""
        try:
            logger.info("Processing chain definitions from: %s", yaml_path)
            with open(yaml_path, "r", encoding="utf-8") as f:
                chain_definitions = yaml.safe_load(f)

            if not isinstance(chain_definitions, list):
                chain_definitions = [chain_definitions]

            for chain_def in chain_definitions:
                try:
                    existing_chain = await self.get_chain_by_name(chain_def["name"])
                    if not existing_chain:
                        await self.create_chain(chain_def)
                        logger.info("Created default chain: %s", chain_def["name"])
                    else:
                        logger.info(
                            "Chain %s already exists, skipping", chain_def["name"]
                        )
                except Exception as e:
                    chain_name = chain_def.get("name", "unknown")
                    logger.error("Failed to create chain %s: %s", chain_name, str(e))

        except Exception as e:
            logger.error(
                "Failed to load chain definitions from %s: %s", yaml_path, str(e)
            )

    async def start(self):
        """Initialize chain storage and create default chains"""
        await self.startup()
        await self.create_default_chains()
