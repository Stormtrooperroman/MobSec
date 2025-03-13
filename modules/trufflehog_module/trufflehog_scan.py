import redis
import json
import os
import asyncio
import logging
import magic
from typing import Dict, Any, List
import zipfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

class TruffleHogModule:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
        self.module_name = "trufflehog_module"


    async def scan_files(self, file_path: str) -> List[Dict]:
        """Scan files using TruffleHog"""
        findings = []
        try:
            cmd = [
                "trufflehog",
                "filesystem",
                "--json",
                "--no-update",
                file_path
            ]
                
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            logger.info(f"TruffleHog output: {stdout.decode()}")
            
            if stdout:
                # TruffleHog outputs one JSON object per line
                for line in stdout.decode().splitlines():
                    try:
                        result = json.loads(line)
                        # Get file path and line number from source metadata
                        source_data = result.get('SourceMetadata', {}).get('Data', {}).get('Filesystem', {})
                        file_name = source_data.get('file', '')
                        line_number = source_data.get('line', 0)
                        
                        # Get the actual secret value
                        raw_secret = result.get('Raw', 'No raw value available')
                        
                        # Convert TruffleHog result to our format
                        finding = {
                            "rule_id": "secret_detection",
                            "name": f"Found {result.get('DetectorName', 'Unknown')} Secret",
                            "severity": "ERROR",
                            "location": {
                                "file": os.path.basename(file_name),
                                "line": line_number,
                                "path": file_name
                            },
                            "metadata": {
                                "description": f"Detected {result.get('DetectorName', 'unknown')} secret pattern",
                                "detector": result.get('DetectorName', ''),
                                "entropy": result.get('Entropy', 0),
                                "category": "secret",
                                "secret_value": raw_secret,
                                "detector_type": result.get('DetectorType', ''),
                                "verified": result.get('Verified', False),
                                "extra_data": result.get('ExtraData', {})
                            }
                        }
                        findings.append(finding)
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.error(f"Error processing finding: {str(e)}")
                            
        except Exception as e:
            logger.error(f"Error during TruffleHog scan: {str(e)}")
            
        return findings

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process the task and return results"""
        file_path = os.path.join("/shared_data", task_data["folder_path"], task_data["file_name"])
        logger.info(f"Processing task for file: {file_path}")
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "error": f"File not found: {file_path}"
            }
            
        try:
            findings = await self.scan_files(file_path)
                
            return {
                "status": "success",
                "results": findings
            }
                
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    async def start(self):
        logger.info(f"Starting {self.module_name} module...")
        while True:
            try:
                queue_key = f"module:{self.module_name}:queue"
                task_id = self.redis_client.lpop(queue_key)
                
                if task_id:
                    try:
                        task_data_str = self.redis_client.get(f"task:{task_id}")
                        if task_data_str:
                            task_data = json.loads(task_data_str)
                            logger.info(f"Processing task {task_id} for file: {task_data.get('file_hash')}")
                            
                            result = await self.process(task_data)
                            
                            # Store result
                            result_key = f"result:{self.module_name}:{task_data['file_hash']}"
                            self.redis_client.set(result_key, json.dumps(result))
                            logger.info(f"Successfully stored result for task {task_id}")
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse task data for task {task_id}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error processing task {task_id}: {str(e)}")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Critical error in module: {str(e)}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    module = TruffleHogModule()
    asyncio.run(module.start()) 