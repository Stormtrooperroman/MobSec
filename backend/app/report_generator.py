import asyncio
import json
import logging
import os
import redis
from typing import Dict, Any, Optional
from app.core.storage import storage
from app.models.storage import ScanStatus
# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self, redis_url: str = None):
        if redis_url is None:
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        
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
            logger.error(f"Error in report generator: {e}")
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
                # FIXED: Update the pattern to match the actual keys in Redis
                cursor = 0
                while True:
                    cursor, keys = self.redis_client.scan(cursor, match="result:*:*", count=100)
                    
                    for key in keys:
                        await self._process_result(key)
                        
                    if cursor == 0:
                        break
                        
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Wait a bit longer if there's an error

    async def _process_result(self, result_key: str):
        """Process a single result from Redis and update the database"""
        try:
            # Extract module name and file hash from the key
            # Format: result:[module_name]:[file_hash]
            parts = result_key.split(":")
            if len(parts) < 3:
                logger.warning(f"Invalid result key format: {result_key}")
                return
            
            module_name = parts[1]
            file_hash = parts[2]
            
            # Get result data from Redis
            result_json = self.redis_client.get(result_key)
            if not result_json:
                logger.warning(f"Result key exists but no data found: {result_key}")
                return
                
            # Parse result data
            try:
                result_data = json.loads(result_json)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON result for {result_key}: {result_json[:100]}...")
                return
            
            # Update file in database with scan results
            await self._update_file_scan_results(file_hash, result_data, module_name)
            
            # Find and delete the associated task
            task_pattern = f"task:*"
            for task_key in self.redis_client.keys(task_pattern):
                task_data = json.loads(self.redis_client.get(task_key))
                if task_data.get('file_hash') == file_hash and task_data.get('module_name') == module_name:
                    self.redis_client.delete(task_key)
                    logger.info(f"Deleted associated task: {task_key}")
            
            # Delete processed result from Redis
            self.redis_client.delete(result_key)
            logger.info(f"Processed and removed result: {result_key}")
            
        except Exception as e:
            logger.error(f"Error processing result {result_key}: {e}")
        

    async def _update_file_scan_results(self, file_hash: str, result_data: Dict[str, Any], module_name: str):
        """Update the file's scan results in the database"""
        try:
            # Get current scan status and results
            file_info = await storage.get_scan_status(file_hash)
            if not file_info:
                logger.warning(f"File not found in database: {file_hash}")
                return
            
            # Log file_info to debug
            logger.info(f"File info structure: {type(file_info)}")
            
            # Determine scan status based on result data
            status = result_data.get('status', 'completed')
            scan_status = (
                ScanStatus.COMPLETED 
                if status.lower() == 'success' or status.lower() == 'completed'
                else ScanStatus.FAILED
            )
            
            if not isinstance(file_info, dict) or file_info.get('scan_results') is None:
                current_results = {}
                logger.info("Initialized empty results dictionary because file_info.scan_results was None")
            else:
                current_results = file_info.get('scan_results', {})
                if not isinstance(current_results, dict):
                    logger.warning(f"scan_results is not a dictionary, got {type(current_results)}")
                    current_results = {}
                                
            # Add module results to the existing scan results
            module_result = {
                'status': status,
                'results': result_data.get('results'),
            }
                        
            # Update or create module results in the overall scan results
            current_results[module_name] = module_result
            
            # Update the database with new results
            success = await storage.update_scan_status(
                file_hash=file_hash,
                status=scan_status,
                results=current_results
            )
            
            if success:
                logger.info(f"Updated scan results for file {file_hash} with {module_name} results")
            else:
                logger.error(f"Failed to update scan results for file {file_hash}")

            chain_key_pattern = f"chain:*"
            for chain_key in self.redis_client.keys(chain_key_pattern):
                chain_data = json.loads(self.redis_client.get(chain_key))
                
                if chain_data.get("file_hash") == file_hash:
                    current_index = chain_data.get("current_index", 0)
                    modules = chain_data.get("modules", [])
                    
                    if current_index < len(modules) and modules[current_index] == module_name:
                        # Update chain data with results and increment current_index
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
                                "file_hash": file_hash
                            })
                        )
                        logger.info(f"Published chain module completion event for {module_name} in chain {chain_task_id}")



        except Exception as e:
            import traceback
            logger.error(f"Exception in _update_file_scan_results: {e}")
            logger.error(traceback.format_exc())


# Singleton instance
report_generator = ReportGenerator()

async def start_report_generator():
    """Start the report generator as a background task"""
    asyncio.create_task(report_generator.start())
    
async def stop_report_generator():
    """Stop the report generator"""
    await report_generator.stop()
