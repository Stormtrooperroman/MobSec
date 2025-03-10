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
        logger.info(f"Starting {self.module_name} module...")
        while True:
            try:
                queue_key = f"module:{self.module_name}:queue"
                task_id = self.redis_client.lpop(queue_key)
                
                if task_id:
                    try:
                        task_data_str = self.redis_client.get(f"task:{task_id}")
                        if not task_data_str:
                            logger.error(f"Task data not found for task_id: {task_id}")
                            continue
                            
                        task_data = json.loads(task_data_str)
                        logger.info(f"Processing task {task_id} for file: {task_data.get('file_hash')}")
                        
                        result = await self.process(task_data)
                        if not result:
                            logger.error(f"No result returned from process for task {task_id}")
                            continue
                        
                        # Store result
                        result_key = f"result:{self.module_name}:{task_data['file_hash']}"
                        self.redis_client.set(result_key, json.dumps(result))
                        logger.info(f"Successfully stored result for task {task_id}")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse task data for task {task_id}: {str(e)}")
                    except redis.RedisError as e:
                        logger.error(f"Redis error while processing task {task_id}: {str(e)}")
                    except Exception as e:
                        import traceback
                        logger.error(f"Error processing task {task_id}: {str(e)}")
                        logger.error(f"Traceback: {traceback.format_exc()}")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                import traceback
                logger.error(f"Critical error in {self.module_name} module main loop: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                await asyncio.sleep(5)  # Back off on critical errors

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        try:
            file_path = os.path.join("/shared_data", task_data["folder_path"], task_data["file_name"])
            logger.info(f"Processing file: {file_path}")
            
            if not os.path.exists(file_path):
                logger.error(f"File not found at path: {file_path}")
                return {
                    "status": "error",
                    "error": f"File not found: {file_path}"
                }
            
            # Only process APK files
            if task_data.get("file_type") != "apk":
                logger.error(f"Invalid file type: {task_data.get('file_type')} for file: {file_path}")
                return {
                    "status": "error",
                    "error": "Permissions module only supports APK files"
                }
            
            try:
                logger.info(f"Analyzing APK permissions for: {file_path}")
                apk = APK(file_path)
                
                declared_perms = apk.get_declared_permissions()
                requested_perms = apk.get_permissions() or []
                
                dangerous = self.get_dangerous_permissions(requested_perms)
                custom = self.get_custom_permissions(requested_perms)
                
                permissions = {
                    "declared": declared_perms,
                    "requested": requested_perms,
                    "dangerous": dangerous,
                    "custom": custom
                }
                
                logger.info(f"Successfully analyzed permissions for {file_path}")
                logger.info(f"Found {len(dangerous)} dangerous permissions and {len(custom)} custom permissions")
                
                return {
                    "status": "success",
                    "results": permissions
                }
                
            except Exception as e:
                import traceback
                logger.error(f"Error analyzing permissions for {file_path}: {str(e)}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                return {
                    "status": "error",
                    "error": f"Permission analysis failed: {str(e)}"
                }
            
        except Exception as e:
            import traceback
            logger.error(f"Critical error in permissions processing: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                "status": "error",
                "error": f"Critical permission analysis error: {str(e)}"
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