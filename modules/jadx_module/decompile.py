import redis
import json
import os
import asyncio
import platform
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import sys

# Configure logging to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class JadxModule:
    def __init__(self):
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        logger.info(f"Connecting to Redis at: {redis_url}")
        try:
            self.redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
            # Test the connection
            self.redis_client.ping()
            logger.info("Successfully connected to Redis")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            sys.exit(1)
            
        self.module_name = "jadx_module"
        self.jadx_timeout = int(os.getenv('JADX_TIMEOUT', 300))

    async def start(self):
        logger.info("Starting JADX module")
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
                "error": "JADX module only supports APK files"
            }
        
        logger.info(f"Processing APK: {file_path}")
        
        # Set up paths
        base_path = f"/shared_data/{task_data['folder_path']}"
        apk_path = file_path
        output_dir = f"{base_path}/java_source"
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Clean output directory if it exists and has content
        if os.path.exists(output_dir) and os.listdir(output_dir):
            logger.info(f"Cleaning output directory: {output_dir}")
            await self.run_async_command(f"rm -rf {output_dir}/*")
        
        # Determine JADX executable path
        jadx_path = await self.get_jadx_path()
        if not jadx_path:
            return {"status": "error", "message": "JADX executable not found"}
        
        logger.info(f"Decompiling APK {task_data['file_name']} to Java with JADX")
        
        # Try decompiling the APK first
        success = await self.run_jadx(jadx_path, output_dir, apk_path)
        
        if not success:
            # If APK decompilation fails, extract all DEX files and try to decompile them
            logger.warning("Decompiling with JADX failed, attempting on all DEX files")
            
            # Extract the APK first
            extract_dir = f"{base_path}/extracted"
            os.makedirs(extract_dir, exist_ok=True)
            
            # Unzip the APK to extract DEX files
            extracted_files = await self.unzip(apk_path, extract_dir)
            
            # Find all DEX files
            dex_files = await self.find_dex_files(extract_dir)
            if not dex_files:
                return {"status": "error", "message": "No DEX files found in APK"}
            
            # Try to decompile each DEX file
            decompile_results = []
            for dex_file in dex_files:
                dex_success = await self.run_jadx(jadx_path, output_dir, dex_file)
                decompile_results.append({"file": dex_file, "success": dex_success})
            
            # Check if any DEX files were successfully decompiled
            if any(result["success"] for result in decompile_results):
                return {
                    "status": "partial_success" if not all(result["success"] for result in decompile_results) else "success",
                    "message": "Decompiled some DEX files successfully",
                    "details": decompile_results
                }
            else:
                return {"status": "error", "message": "Failed to decompile all DEX files"}
        
        return {"status": "success", "message": "APK decompiled successfully"}

    async def run_jadx(self, jadx_path: str, output_dir: str, input_file: str) -> bool:
        """Run JADX decompilation on a file"""
        try:
            logger.info(f"Running JADX on {os.path.basename(input_file)}")
            
            # Make sure JADX is executable
            if not os.access(jadx_path, os.X_OK):
                os.chmod(jadx_path, os.stat(jadx_path).st_mode | stat.S_IEXEC)
            
            # Run jadx decompilation asynchronously
            process = await asyncio.create_subprocess_exec(
                jadx_path, 
                '-ds', output_dir,
                '-q', '-r', '--show-bad-code',
                input_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.jadx_timeout)
                success = process.returncode == 0
                
                if success:
                    logger.info(f"Successfully decompiled {os.path.basename(input_file)}")
                elif stderr.decode() == '':
                    success = True
                    logger.info(f"Decompiled {os.path.basename(input_file)} with errors")
                else:
                    logger.info(stderr)
                    stderr_text = stderr.decode() if stderr else "Unknown error"
                    logger.error(f"Failed to decompile {os.path.basename(input_file)}: {stderr_text}")
                
                return success
            except asyncio.TimeoutError:
                # If process times out, kill it
                process.kill()
                logger.warning(f"JADX decompilation timed out for {input_file}")
                return False
                
        except Exception as e:
            logger.exception(f"Error running JADX on {input_file}")
            return False

    async def get_jadx_path(self) -> Optional[str]:
        """Determine the JADX executable path based on the platform"""
        # Check environment variable first
        jadx_binary = os.getenv('JADX_BINARY')
        if jadx_binary and os.path.isfile(jadx_binary):
            return jadx_binary
            
        # Check in /opt/jadx/bin which is set in the Dockerfile
        if platform.system() == 'Windows':
            jadx_path = '/opt/jadx/bin/jadx.bat'
        else:
            jadx_path = '/opt/jadx/bin/jadx'
            
        if os.path.isfile(jadx_path):
            return jadx_path
            
        # As a last resort, try to find in PATH
        which_result = shutil.which('jadx')
        return which_result

    async def unzip(self, app_path: str, ext_path: str) -> List[str]:
        """Unzip APK file to extract DEX files"""
        logger.info(f"Unzipping {app_path} to {ext_path}")
        
        files = []
        try:
            # Create extraction directory if it doesn't exist
            os.makedirs(ext_path, exist_ok=True)
            
            with zipfile.ZipFile(app_path, 'r') as zipptr:
                files = zipptr.namelist()
                for fileinfo in zipptr.infolist():
                    # Skip directories
                    if fileinfo.filename.endswith('/'):
                        continue
                        
                    # Skip encrypted files
                    if fileinfo.flag_bits & 0x1:
                        logger.warning(f"Skipping encrypted file {fileinfo.filename}")
                        continue
                    
                    # Extract the file
                    try:
                        zipptr.extract(fileinfo.filename, ext_path)
                    except Exception as e:
                        logger.warning(f"Failed to extract {fileinfo.filename}: {str(e)}")
        except Exception as e:
            logger.error(f"Error unzipping {app_path}: {str(e)}")
            
            # Fallback to OS unzip
            files = await self.os_unzip(app_path, ext_path)
            
        return files

    async def os_unzip(self, app_path: str, ext_path: str) -> List[str]:
        """Fallback to OS unzip utility"""
        logger.info("Attempting to unzip with OS unzip utility")
        
        try:
            if platform.system() == 'Windows':
                logger.warning("OS Unzip not implemented for Windows")
                return []
                
            unzip_path = shutil.which('unzip')
            if not unzip_path:
                logger.warning("OS Unzip utility not found")
                return []
                
            # Execute the unzip command
            process = await asyncio.create_subprocess_exec(
                unzip_path, '-o', '-q', app_path, '-d', ext_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            # List files in the unzipped directory
            list_process = await asyncio.create_subprocess_exec(
                unzip_path, '-qq', '-l', app_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await list_process.communicate()
            file_list = stdout.decode('utf-8', errors='replace').split('\n')
            
            return file_list
            
        except Exception as e:
            logger.exception("Unzipping Error with OS unzip utility")
            return []

    async def find_dex_files(self, base_dir: str) -> List[str]:
        """Find all DEX files in the directory structure"""
        dex_files = []
        
        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.lower().endswith('.dex'):
                    dex_files.append(os.path.join(root, file))
                    
        logger.info(f"Found {len(dex_files)} DEX files")
        return dex_files

    async def run_async_command(self, command: str) -> bool:
        """Run a shell command asynchronously"""
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Error running command '{command}': {str(e)}")
            return False


if __name__ == "__main__":
    logger.info("Starting JADX module script")
    module = JadxModule()
    asyncio.run(module.start())