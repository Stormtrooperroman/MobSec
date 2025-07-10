import os
import json
import uuid
import logging
from redis import Redis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from app.models.chain import (
    Chain,
    Module,
    Base,
    chain_modules,
    ChainExecution,
    ModuleExecution,
    ChainStatus,
)
from app.core.app_manager import storage
from datetime import datetime, timezone
import asyncio
import yaml
from app.modules.module_manager import ModuleManager
import httpx
from app.core.settings_db import init_db

logger = logging.getLogger(__name__)


class ChainManager:
    def __init__(self):
        database_url = os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://postgres:password@db:5432/mobsec_db"
        )
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        self.engine = create_async_engine(database_url, echo=True)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        self.redis = Redis.from_url(redis_url, decode_responses=True)

        self.chain_event_queue = asyncio.Queue()

        self.loop = asyncio.get_running_loop()

        modules_path = os.getenv("MODULES_PATH", "/app/modules")
        self.module_manager = ModuleManager(
            redis_url=redis_url, modules_path=modules_path
        )

        self._setup_chain_event_monitor()

        asyncio.create_task(self._process_chain_event_queue())

        self.http_client = httpx.AsyncClient(timeout=120.0)

    async def _process_chain_event_queue(self):
        """Process chain events from the queue in the main event loop"""
        while True:
            try:
                event = await self.chain_event_queue.get()
                chain_task_id = event.get("chain_task_id")
                next_module_index = event.get("next_module_index")
                file_hash = event.get("file_hash")
                if chain_task_id and next_module_index is not None and file_hash:
                    lock_key = f"lock:chain:{chain_task_id}:module:{next_module_index}"

                    lock_acquired = self.redis.setnx(lock_key, "locked")

                    if lock_acquired:
                        self.redis.expire(lock_key, 3600)

                        chain_data = json.loads(
                            self.redis.get(f"chain:{chain_task_id}")
                        )
                        modules = chain_data.get("modules", [])

                        self.redis.delete(f"chain:module:completed:{chain_task_id}")

                        if next_module_index < len(modules):
                            is_running = await self._is_module_already_running(
                                chain_task_id, next_module_index
                            )

                            if not is_running:
                                await self._start_module(
                                    chain_task_id, next_module_index, file_hash
                                )
                            else:
                                logger.info(
                                    f"Module {next_module_index} for chain {chain_task_id} is already running, skipping"
                                )
                        else:
                            await self._complete_chain(chain_task_id)
                    else:
                        logger.info(
                            f"Duplicate event for chain {chain_task_id}, module {next_module_index} - skipping"
                        )

                self.chain_event_queue.task_done()
            except Exception as e:
                logger.error(f"Error processing chain event from queue: {str(e)}")

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

    def _setup_chain_event_monitor(self):
        """Setup Redis subscription for chain events"""
        import threading

        def monitor_chain_events():
            pubsub = self.redis.pubsub()
            pubsub.psubscribe("chain:module:completed:*")

            logger.info("Starting Redis chain event monitor")
            for message in pubsub.listen():
                if message["type"] == "pmessage":
                    try:
                        data = json.loads(message["data"])

                        asyncio.run_coroutine_threadsafe(
                            self.chain_event_queue.put(data), self.loop
                        )
                    except Exception as e:
                        logger.error(f"Error adding chain event to queue: {str(e)}")

        monitor_thread = threading.Thread(target=monitor_chain_events, daemon=True)
        monitor_thread.start()

    async def init_db(self):
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
            chains_stmt = select(Chain)
            chains_result = await session.execute(chains_stmt)
            chains = chains_result.scalars().all()

            chains_with_modules = []

            for chain in chains:
                modules_stmt = (
                    select(Module, chain_modules.c.order, chain_modules.c.parameters)
                    .join(chain_modules, Module.name == chain_modules.c.module_name)
                    .where(chain_modules.c.chain_name == chain.name)
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
                chains_with_modules.append(chain_dict)

            return chains_with_modules

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

        self.redis.set(
            f"chain:{task_id}",
            json.dumps(
                {
                    "chain_name": chain_name,
                    "file_hash": file_hash,
                    "modules": [m["module"]["name"] for m in modules],
                    "current_index": 0,
                    "results": {},
                    "file_type": file_info.get("file_type", "unknown"),
                    "folder_path": folder,
                    "file_name": file_info.get("original_name", ""),
                }
            ),
            ex=86400,
        )

        await self._start_module(task_id, 0, file_hash)

        return {
            "status": "success",
            "message": f"Chain '{chain_name}' execution started for file {file_hash}",
            "task_id": task_id,
        }

    async def _start_module(self, chain_task_id, module_index, file_hash):
        """Start execution of a specific module in the chain"""
        try:
            chain_data = self.redis.get(f"chain:{chain_task_id}")
            if not chain_data:
                raise ValueError(f"Chain data not found for task {chain_task_id}")

            chain_data = json.loads(chain_data)

            data = {
                "folder_path": chain_data["folder_path"],
                "file_name": chain_data["file_name"],
                "file_type": chain_data["file_type"],
                "created_at": datetime.now(timezone.utc).timestamp(),
            }

            module_name = chain_data["modules"][module_index]

            if module_name.startswith("external:"):
                """
                This part for future update and now it doesn't work
                """
                pass
            else:
                module_task_id = await self.module_manager.submit_task(
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

                logger.info(f"Started module {module_name} for chain {chain_task_id}")

        except Exception as e:
            logger.error(f"Error starting module: {str(e)}")
            await self._fail_module(chain_task_id, module_index, str(e))

            if module_task_id:
                self.redis.delete(f"task:{module_task_id}")

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

            chain_data = self.redis.get(f"chain:{chain_task_id}")
            if chain_data:
                chain_data = json.loads(chain_data)
                file_hash = chain_data.get("file_hash")

                for module_name in chain_data.get("modules", []):
                    self.redis.delete(f"result:{module_name}:{file_hash}")
                    for task_key in self.redis.scan_iter("task:*"):
                        try:
                            task_data = json.loads(self.redis.get(task_key))
                            if (
                                task_data.get("file_hash") == file_hash
                                and task_data.get("module_name") == module_name
                            ):
                                self.redis.delete(task_key)
                        except:
                            continue

            for key in self.redis.scan_iter(f"*{chain_task_id}*"):
                self.redis.delete(key)

            logger.info(f"Chain {chain_task_id} completed successfully")
        except Exception as e:
            logger.error(f"Error completing chain {chain_task_id}: {str(e)}")

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

            chain_data = self.redis.get(f"chain:{chain_task_id}")
            if chain_data:
                chain_data = json.loads(chain_data)
                file_hash = chain_data.get("file_hash")

                for module_name in chain_data.get("modules", []):
                    self.redis.delete(f"result:{module_name}:{file_hash}")
                    for task_key in self.redis.scan_iter("task:*"):
                        try:
                            task_data = json.loads(self.redis.get(task_key))
                            if (
                                task_data.get("file_hash") == file_hash
                                and task_data.get("module_name") == module_name
                            ):
                                self.redis.delete(task_key)
                        except:
                            continue

            for key in self.redis.scan_iter(f"*{chain_task_id}*"):
                self.redis.delete(key)

            logger.error(f"Chain {chain_task_id} failed: {error_message}")
        except Exception as e:
            logger.error(f"Error failing chain {chain_task_id}: {str(e)}")

    async def _fail_module(self, chain_task_id, module_index, error_message):
        """Mark module as failed"""
        async with self.async_session() as session:
            module_execution_id = f"{chain_task_id}_module_{module_index}"
            module_execution = await session.execute(
                select(ModuleExecution).where(ModuleExecution.id == module_execution_id)
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
                logger.info(f"Relinking chain {chain.name} with modules")

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
                                    f"Relinked module {module_name} to chain {chain.name}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to relink module {module_name} to chain {chain.name}: {str(e)}"
                                )
                        else:
                            logger.warning(
                                f"Module {module_name} not found for chain {chain.name}"
                            )

            await session.commit()
            logger.info("Chain module relinking completed")

    async def create_default_chains(self):
        """Create default chains from YAML files in root modules folder"""
        modules_path = os.getenv("MODULES_PATH", "./app/modules")
        logger.info(f"Looking for chain definitions in: {modules_path}")

        try:
            files = os.listdir(modules_path)
            logger.info(f"Found files in directory: {files}")

            for file_name in files:
                if file_name.endswith(".yaml") and not file_name == "config.yaml":
                    yaml_path = os.path.join(modules_path, file_name)
                    logger.info(f"Processing chain file: {yaml_path}")
                    await self._process_chain_yaml(yaml_path)

        except Exception as e:
            logger.error(f"Error processing chain definitions: {str(e)}")

    async def _process_chain_yaml(self, yaml_path: str):
        """Process a YAML file containing chain definitions"""
        try:
            logger.info(f"Processing chain definitions from: {yaml_path}")
            with open(yaml_path, "r") as f:
                chain_definitions = yaml.safe_load(f)

            if not isinstance(chain_definitions, list):
                chain_definitions = [chain_definitions]

            for chain_def in chain_definitions:
                try:
                    existing_chain = await self.get_chain_by_name(chain_def["name"])
                    if not existing_chain:
                        await self.create_chain(chain_def)
                        logger.info(f"Created default chain: {chain_def['name']}")
                    else:
                        logger.info(
                            f"Chain {chain_def['name']} already exists, skipping"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to create chain {chain_def.get('name', 'unknown')}: {str(e)}"
                    )

        except Exception as e:
            logger.error(f"Failed to load chain definitions from {yaml_path}: {str(e)}")

    async def start(self):
        """Initialize chain storage and create default chains"""
        await self.create_default_chains()
