import asyncio
import logging
import os
import traceback
from typing import Any, Dict, Optional

from app.core.app_manager import storage
from app.models.app import ScanStatus

from app.services.redis_service import RedisService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

        self.redis_service = RedisService(redis_url)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background report generator service"""
        logger.info("Starting Report Generator service")
        self.running = True
        try:
            async for key in self.redis_service.iter_result_keys():
                await self._process_result(key)

            await self._monitor_results_events()
        except asyncio.CancelledError:
            logger.info("Report generator stopped")
            raise
        except Exception as e:
            logger.error("Error in report generator: %s", e)
            self.running = False
            raise

    async def stop(self):
        """Stop the background service"""
        logger.info("Stopping Report Generator service")
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.debug("Report generator task ended with: %s", e)

        await self.redis_service.close()

    async def _monitor_results_events(self):
        """Process new results as modules write them, via Redis keyspace
        notifications.
        """
        try:
            async for key in self.redis_service.listen_result_keys():
                if not self.running:
                    break
                await self._process_result(key)
        except asyncio.CancelledError:
            logger.info("Report generator event listener cancelled")
            raise
        except Exception as e:
            logger.error("Error in result event listener: %s", e)
            raise

    async def _process_result(self, result_key: str):
        """Process a single result from Redis and update the database"""
        try:
            parsed = self.redis_service.parse_result_key(result_key)
            if parsed is None:
                logger.warning("Invalid result key format: %s", result_key)
                return

            module_name, file_hash = parsed

            result_data = await self.redis_service.get_json(result_key)
            if result_data is None:
                logger.warning(
                    "Result key exists but no usable data found: %s", result_key
                )
                return

            # Update file in database with scan results
            await self._update_file_scan_results(file_hash, result_data, module_name)

            cleaned = await self.redis_service.delete_tasks_for(
                file_hash, module_name=module_name, case_insensitive=True
            )
            if cleaned:
                logger.info("Cleaned up %s associated task(s)", cleaned)

            # Delete processed result from Redis
            await self.redis_service.delete(result_key)
            logger.info("Processed and removed result: %s", result_key)

        except Exception as e:
            logger.error("Error processing result %s: %s", result_key, e)

    async def _update_file_scan_results(
        self, file_hash: str, result_data: Dict[str, Any], module_name: str
    ):
        """Update the file's scan results in the database"""
        try:
            current_results = await self._get_or_create_scan_results(file_hash)
            if current_results is None:
                return

            # Determine scan status based on result data
            status = result_data.get("status", "completed")
            scan_status = (
                ScanStatus.COMPLETED
                if status.lower() in ("success", "completed")
                else ScanStatus.FAILED
            )

            # Add module results to the existing scan results
            module_result = {
                "status": status,
                "results": result_data.get("results"),
            }
            current_results[module_name] = module_result

            # Update the database with new results
            success = await storage.update_scan_status(
                file_hash=file_hash, status=scan_status, results=current_results
            )

            if success:
                logger.info(
                    "Updated scan results for file %s with %s results",
                    file_hash,
                    module_name,
                )
            else:
                logger.error("Failed to update scan results for file %s", file_hash)

            await self._update_chains_for_result(file_hash, module_name, result_data)

        except Exception as e:
            logger.error("Exception in _update_file_scan_results: %s", e)
            logger.error(traceback.format_exc())

    async def _get_or_create_scan_results(self, file_hash: str):
        """Get or create scan results for a file hash"""
        file_info = await storage.get_scan_status(file_hash)
        if not file_info:
            logger.warning("File not found in database: %s", file_hash)
            return None

        logger.info("File info structure: %s", type(file_info))

        if not isinstance(file_info, dict) or file_info.get("scan_results") is None:
            logger.info(
                "Initialized empty results dictionary because file_info.scan_results was None"
            )
            return {}

        current_results = file_info.get("scan_results", {})
        if not isinstance(current_results, dict):
            logger.warning(
                "scan_results is not a dictionary, got %s", type(current_results)
            )
            return {}

        return current_results

    async def _update_chains_for_result(
        self, file_hash: str, module_name: str, result_data: Dict[str, Any]
    ):
        """Update chain data for a module result"""
        async for chain_task_id, chain_data in self.redis_service.iter_chain_states():
            try:
                if chain_data.get("file_hash") != file_hash:
                    continue

                current_index = chain_data.get("current_index", 0)
                modules = chain_data.get("modules", [])

                if (
                    current_index < len(modules)
                    and modules[current_index] == module_name
                ):
                    await self._process_chain_module_completion(
                        chain_task_id, chain_data, module_name, result_data
                    )
            except KeyError as e:
                logger.error("Error processing chain %s: %s", chain_task_id, e)

    async def _process_chain_module_completion(
        self,
        chain_task_id: str,
        chain_data: dict,
        module_name: str,
        result_data: Dict[str, Any],
    ):
        """Process a completed module in a chain"""
        current_index = chain_data.get("current_index", 0)
        file_hash = chain_data.get("file_hash", "")

        chain_data["results"][module_name] = result_data
        chain_data["current_index"] = current_index + 1

        await self.redis_service.set_chain_state(chain_task_id, chain_data)

        next_module_index = current_index + 1
        await self.redis_service.publish_chain_event(
            chain_task_id,
            {
                "chain_task_id": chain_task_id,
                "module_index": current_index,
                "next_module_index": next_module_index,
                "file_hash": file_hash,
            },
        )
        logger.info(
            "Published chain module completion event for %s in chain %s",
            module_name,
            chain_task_id,
        )


# Singleton instance
report_generator = ReportGenerator()


async def start_report_generator():
    """Start the report generator as a background task"""
    report_generator._task = asyncio.create_task(report_generator.start())


async def stop_report_generator():
    """Stop the report generator"""
    await report_generator.stop()
