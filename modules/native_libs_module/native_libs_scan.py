import redis
import json
import os
import asyncio
from typing import Dict, Any, List
import logging
import magic
import lief
from androguard.core.apk import APK

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

class NativeLibsModule:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
        self.module_name = "native_libs_module"
        
    async def start(self):
        logger.info("Starting Native Libraries Analysis module...")
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
                "error": "Native Libraries module only supports APK files"
            }
            
        try:
            apk = APK(file_path)
            native_libs = apk.get_libraries()
            
            results = {
                "status": "success",
                "results": {
                    "libraries": [],
                    "summary": {
                        "total_libs": 0,
                        "architectures": {}
                    }
                }
            }
            
            # Get all files from APK
            for file_name in apk.get_files():
                # Check if file is in lib directory and is a shared library
                if file_name.startswith('lib/') and file_name.endswith('.so'):
                    try:
                        # Extract library data
                        lib_data = apk.get_file(file_name)
                        if lib_data:
                            lib_info = self.analyze_native_lib(lib_data, file_name)
                            if lib_info:
                                results["results"]["libraries"].append(lib_info)
                    except Exception as e:
                        logger.warning(f"Failed to analyze library {file_name}: {str(e)}")
                        results["results"]["libraries"].append({
                            "name": file_name,
                            "error": str(e)
                        })
            
            # Count valid architectures (exclude entries with errors)
            valid_libs = [lib for lib in results["results"]["libraries"] if 'error' not in lib]
            
            results["results"]["summary"]["total_libs"] = len(results["results"]["libraries"])
            results["results"]["summary"]["architectures"] = self.count_architectures(valid_libs)
            
            return results
            
        except Exception as e:
            logger.error(f"Error analyzing native libraries: {str(e)}")
            return {
                "status": "error",
                "error": f"Failed to analyze native libraries: {str(e)}",
                "results": {
                    "libraries": [],
                    "summary": {
                        "total_libs": 0,
                        "architectures": {}
                    }
                }
            }

    def analyze_native_lib(self, lib_data: bytes, lib_name: str) -> Dict[str, Any]:
        try:
            # Save library temporarily for analysis
            temp_path = f"/tmp/{os.path.basename(lib_name)}"
            with open(temp_path, 'wb') as f:
                f.write(lib_data)
            
            # Get file type
            file_type = magic.from_file(temp_path)
            
            # Only analyze ELF files
            if "ELF" not in file_type:
                os.remove(temp_path)
                return {
                    "name": lib_name,
                    "error": "Not an ELF file",
                    "type": file_type
                }
            
            # Analyze with LIEF
            try:
                binary = lief.parse(temp_path)
                if binary is None:
                    raise ValueError("Failed to parse binary")
                    
                result = {
                    "name": lib_name,
                    "type": file_type,
                    "symbols": len(binary.exported_functions),
                    "imported_functions": len(binary.imported_functions),
                    "sections": len(binary.sections),
                    "has_debug_symbols": self.has_debug_symbols(binary),
                    "imported_libraries": [lib.name for lib in binary.imported_libraries],
                    "exported_functions": [func.name for func in binary.exported_functions]
                }
            except Exception as e:
                result = {
                    "name": lib_name,
                    "error": f"LIEF analysis failed: {str(e)}",
                    "type": file_type
                }
            
            # Clean up temp file
            os.remove(temp_path)
            return result
            
        except Exception as e:
            logger.warning(f"Error analyzing library {lib_name}: {str(e)}")
            return {
                "name": lib_name,
                "error": str(e)
            }

    def has_debug_symbols(self, binary) -> bool:
        return any(section.type == lief.ELF.SECTION_TYPES.SYMTAB for section in binary.sections)

    def count_architectures(self, lib_details: List[Dict]) -> Dict[str, int]:
        arch_count = {}
        for lib in lib_details:
            if 'architecture' in lib:
                arch = lib['architecture']
                arch_count[arch] = arch_count.get(arch, 0) + 1
        return arch_count

if __name__ == "__main__":
    module = NativeLibsModule()
    asyncio.run(module.start())