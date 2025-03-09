import redis
import json
import os
import asyncio
from typing import Dict, Any
import logging
from androguard.core.apk import APK

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

class PermissionsModule:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
        self.module_name = "permissions_module"
        
    async def start(self):
        logger.info("Starting Permissions Analysis module...")
        while True:
            try:
                # Get tasks from module queue
                queue_key = f"module:{self.module_name}:queue"
                task_id = self.redis_client.lpop(queue_key)
                
                if task_id:
                    # Get task data
                    task_data_str = self.redis_client.get(f"task:{task_id}")
                    if task_data_str:
                        task_data = json.loads(task_data_str)
                        result = await self.process(task_data)
                        
                        # Store result
                        result_key = f"result:{self.module_name}:{task_data['file_hash']}"
                        self.redis_client.set(result_key, json.dumps(result))
                        logger.info(f"Stored result for task {task_id}")
                
                await asyncio.sleep(1)  # Prevent tight loop
                
            except Exception as e:
                logger.error(f"Error in module loop: {str(e)}")
                await asyncio.sleep(5)  # Back off on errors

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        file_path = os.path.join("/shared_data", task_data["folder_path"], task_data["file_name"])
        
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "error": f"File not found: {file_path}"
            }
        
        # Only process APK files
        if task_data.get("file_type") != "apk":
            return {
                "status": "error",
                "error": "Permissions module only supports APK files"
            }
            
        try:
            apk = APK(file_path)
            
            permissions = {
                "declared": apk.get_permissions(),
                "requested": apk.get_requested_permissions() or [],
                "required": apk.get_requested_permissions_or_apis() or []
            }
            
            return {
                "status": "success",
                "results": permissions
            }
            
        except Exception as e:
            logger.error(f"Error analyzing permissions: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    def get_dangerous_permissions(self, permissions):
        dangerous_permissions = [
            "android.permission.READ_CALENDAR",
            "android.permission.WRITE_CALENDAR",
            "android.permission.CAMERA",
            "android.permission.READ_CONTACTS",
            "android.permission.WRITE_CONTACTS",
            "android.permission.GET_ACCOUNTS",
            "android.permission.ACCESS_FINE_LOCATION",
            "android.permission.ACCESS_COARSE_LOCATION",
            "android.permission.RECORD_AUDIO",
            "android.permission.READ_PHONE_STATE",
            "android.permission.READ_PHONE_NUMBERS",
            "android.permission.CALL_PHONE",
            "android.permission.ANSWER_PHONE_CALLS",
            "android.permission.READ_CALL_LOG",
            "android.permission.WRITE_CALL_LOG",
            "android.permission.ADD_VOICEMAIL",
            "android.permission.USE_SIP",
            "android.permission.PROCESS_OUTGOING_CALLS",
            "android.permission.BODY_SENSORS",
            "android.permission.SEND_SMS",
            "android.permission.RECEIVE_SMS",
            "android.permission.READ_SMS",
            "android.permission.RECEIVE_WAP_PUSH",
            "android.permission.RECEIVE_MMS",
            "android.permission.READ_EXTERNAL_STORAGE",
            "android.permission.WRITE_EXTERNAL_STORAGE"
        ]
        return [p for p in permissions if p in dangerous_permissions]

    def get_custom_permissions(self, permissions):
        return [p for p in permissions if not p.startswith('android.permission.')]

if __name__ == "__main__":
    module = PermissionsModule()
    asyncio.run(module.start())