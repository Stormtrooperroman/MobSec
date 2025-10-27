import asyncio
import json
import logging
import os
import traceback
from typing import Any, Dict

import redis

from app.core.app_manager import storage
from app.models.app import ScanStatus


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

        self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        self.running = False
        self.polling_interval = 2  # seconds

    async def start(self):
        """Start the background report generator service"""
        logger.info("Starting Report Generator service")
        self.running = True
        try:
            await self._monitor_results_loop()
        except Exception as e:
            logger.error("Error in report generator: %s", e)
            self.running = False
            raise

    async def stop(self):
        """Stop the background service"""
        logger.info("Stopping Report Generator service")
        self.running = False

    async def _monitor_results_loop(self):
        """Main loop to continuously check for new results in Redis"""
        while self.running:
            try:
                # Scan for all keys matching the result pattern
                cursor = 0
                while True:
                    cursor, keys = self.redis_client.scan(
                        cursor, match="result:*:*", count=100
                    )

                    for key in keys:
                        await self._process_result(key)

                    if cursor == 0:
                        break

                await asyncio.sleep(self.polling_interval)

            except Exception as e:
                logger.error("Error in monitoring loop: %s", e)
                await asyncio.sleep(5)  # Wait a bit longer if there's an error

    async def _process_result(self, result_key: str):
        """Process a single result from Redis and update the database"""
        try:
            # Extract module name and file hash from the key
            # Format: result:[module_name]:[file_hash]
            parts = result_key.split(":")
            if len(parts) < 3:
                logger.warning("Invalid result key format: %s", result_key)
                return

            module_name = parts[1]
            file_hash = parts[2]

            # Get result data from Redis
            result_json = self.redis_client.get(result_key)
            if not result_json:
                logger.warning("Result key exists but no data found: %s", result_key)
                return

            # Parse result data
            try:
                result_data = json.loads(result_json)
            except json.JSONDecodeError:
                logger.error(
                    "Failed to parse JSON result for %s: %s...", result_key, result_json[:100]
                )
                return

            # Update file in database with scan results
            await self._update_file_scan_results(file_hash, result_data, module_name)

            # Clean up any associated tasks
            task_keys = self.redis_client.keys("task:*")
            for task_key in task_keys:
                try:
                    task_data = json.loads(self.redis_client.get(task_key))
                    if (
                        task_data.get("file_hash") == file_hash
                        and task_data.get("module_name", "").lower()
                        == module_name.lower()
                    ):
                        self.redis_client.delete(task_key)
                        logger.info("Cleaned up associated task: %s", task_key)
                except json.JSONDecodeError:
                    logger.warning("Could not parse task data for %s", task_key)
                except Exception as e:
                    logger.error(
                        "Error processing task cleanup for %s: %s", task_key, e
                    )

            # Delete processed result from Redis
            self.redis_client.delete(result_key)
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
                    "Updated scan results for file %s with %s results", file_hash, module_name
                )
            else:
                logger.error("Failed to update scan results for file %s", file_hash)

            # Update chains if applicable
            self._update_chains_for_result(file_hash, module_name, result_data)

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

    def _update_chains_for_result(
        self, file_hash: str, module_name: str, result_data: Dict[str, Any]
    ):
        """Update chain data for a module result"""
        chain_key_pattern = "chain:*"
        for chain_key in self.redis_client.keys(chain_key_pattern):
            try:
                chain_data = json.loads(self.redis_client.get(chain_key))
                if chain_data.get("file_hash") != file_hash:
                    continue

                current_index = chain_data.get("current_index", 0)
                modules = chain_data.get("modules", [])

                if (
                    current_index < len(modules)
                    and modules[current_index] == module_name
                ):
                    self._process_chain_module_completion(
                        chain_key, chain_data, module_name, result_data
                    )
            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Error processing chain %s: %s", chain_key, e)

    def _process_chain_module_completion(
        self, chain_key: str, chain_data: dict, module_name: str,
        result_data: Dict[str, Any]
    ):
        """Process a completed module in a chain"""
        current_index = chain_data.get("current_index", 0)
        file_hash = chain_data.get("file_hash", "")
        
        chain_data["results"][module_name] = result_data
        chain_data["current_index"] = current_index + 1
        chain_task_id = chain_key.split(":")[-1]
        
        self.redis_client.set(chain_key, json.dumps(chain_data), ex=86400)

        next_module_index = current_index + 1
        self.redis_client.publish(
            f"chain:module:completed:{chain_task_id}",
            json.dumps({
                "chain_task_id": chain_task_id,
                "module_index": current_index,
                "next_module_index": next_module_index,
                "file_hash": file_hash,
            }),
        )
        logger.info(
            "Published chain module completion event for %s in chain %s",
            module_name, chain_task_id
        )


# Singleton instance
report_generator = ReportGenerator()


async def start_report_generator():
    """Start the report generator as a background task"""
    asyncio.create_task(report_generator.start())


async def stop_report_generator():
    """Stop the report generator"""
    await report_generator.stop()
