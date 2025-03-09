import redis
import json
import os
import asyncio
from typing import Dict, Any, List
import logging
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

class APKiDModule:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
        self.module_name = "apkid_module"
        
        # Verify APKiD installation
        try:
            result = subprocess.run(['apkid', '--version'], capture_output=True, text=True)
            logger.info(f"APKiD version: {result.stdout.strip()}")
        except Exception as e:
            logger.error(f"APKiD verification failed: {str(e)}")
            sys.exit(1)
        
    async def start(self):
        logger.info("Starting APKiD module...")
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
        
        logger.info(f"Processing file: {file_path}")
        
        if not os.path.exists(file_path):
            return {
                "status": "error",
                "error": f"File not found: {file_path}"
            }
        
        # Only process APK files
        if task_data.get("file_type") != "apk":
            return {
                "status": "error",
                "error": "APKiD module only supports APK files"
            }
        
        try:
            # Run APKiD scan asynchronously
            process = await asyncio.create_subprocess_exec(
                'apkid',
                '--json',
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return {
                    "status": "error",
                    "error": f"APKiD scan failed: {stderr.decode()}"
                }
            
            # Parse APKiD results
            apkid_results = json.loads(stdout.decode())
            
            # Format results
            formatted_results = {
                "matches": [],
                "metadata": {}
            }
            
            # Process APKiD results
            for file_path, file_results in apkid_results.get("files", {}).items():
                matches = file_results.get("matches", {})
                for match_type, match_list in matches.items():
                    formatted_results["matches"].append({
                        "file": file_path,
                        "type": match_type,
                        "findings": match_list
                    })
                
                # Add metadata if present
                metadata = file_results.get("metadata", {})
                if metadata:
                    formatted_results["metadata"][file_path] = metadata
            
            return {
                "status": "success",
                "results": formatted_results
            }
            
        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    def summarize_results(self, scan_results: Dict) -> Dict[str, Any]:
        categories = {
            "packers": {},
            "compilers": {},
            "obfuscators": {},
            "abnormalities": {},
            "anti_vm": {},
            "anti_disassembly": {},
            "manipulators": {},
            "protectors": {}
        }
        
        # Process all files in the results
        for file_info in scan_results.get('files', []):
            matches = file_info.get('matches', {})
            
            # Group findings by category
            for category, items in matches.items():
                if category == 'compiler':
                    for item in items:
                        categories["compilers"][item] = categories["compilers"].get(item, 0) + 1
                elif category == 'packer':
                    for item in items:
                        categories["packers"][item] = categories["packers"].get(item, 0) + 1
                elif category == 'obfuscator':
                    for item in items:
                        categories["obfuscators"][item] = categories["obfuscators"].get(item, 0) + 1
                elif category == 'abnormality':
                    for item in items:
                        categories["abnormalities"][item] = categories["abnormalities"].get(item, 0) + 1
                elif category == 'anti_vm':
                    for item in items:
                        categories["anti_vm"][item] = categories["anti_vm"].get(item, 0) + 1
                elif category == 'anti_disassembly':
                    for item in items:
                        categories["anti_disassembly"][item] = categories["anti_disassembly"].get(item, 0) + 1
                elif category == 'manipulator':
                    for item in items:
                        categories["manipulators"][item] = categories["manipulators"].get(item, 0) + 1
                elif category == 'protector':
                    for item in items:
                        categories["protectors"][item] = categories["protectors"].get(item, 0) + 1
                # Add other categories to their respective dictionaries
                elif category not in ['compiler', 'packer', 'obfuscator', 'abnormality', 'anti_vm', 'anti_disassembly', 'manipulator', 'protector']:
                    # Handle any other categories that might appear in the results
                    if category not in categories:
                        categories[category] = {}
                    
                    for item in items:
                        categories[category][item] = categories[category].get(item, 0) + 1
        
        return categories

    def process_findings(self, scan_results: Dict) -> List[Dict]:
        processed_findings = []
        logger.info(scan_results)
        # Process all files in the results
        for file_info in scan_results.get('files', []):
            filename = file_info.get('filename', 'unknown')
            matches = file_info.get('matches', {})
            
            # Determine file type based on filename
            file_type = "unknown"
            if filename.endswith('.apk'):
                file_type = "apk"
            elif filename.endswith('.dex') or '!classes.dex' in filename:
                file_type = "dex"
            elif filename.endswith('.so'):
                file_type = "native_library"
            elif filename.endswith('.jar'):
                file_type = "jar"
            
            # Process each category of findings
            for category, items in matches.items():
                for item in items:
                    # Determine severity based on finding category
                    severity = self.determine_severity(category, item)
                    
                    finding = {
                        "rule_id": category,
                        "name": item,
                        "severity": severity,
                        "location": {
                            "file": filename,
                            "type": file_type
                        },
                        "metadata": {
                            "description": self.get_description(category, item)
                        }
                    }
                    processed_findings.append(finding)
                        
        return processed_findings
    
    def determine_severity(self, category: str, item: str) -> str:
        """Determine severity based on finding category and specific item"""
        high_severity_categories = ['packer', 'anti_vm', 'anti_disassembly', 'protector']
        medium_severity_categories = ['obfuscator', 'manipulator']
        
        # Check for specific high-severity items
        high_severity_keywords = ['malicious', 'exploit', 'vulnerability', 'dangerous']
        if any(keyword in item.lower() for keyword in high_severity_keywords):
            return "ERROR"
            
        # Category-based severity
        if category in high_severity_categories:
            return "WARNING"
        elif category in medium_severity_categories:
            return "WARNING"
        elif category == 'abnormality':
            return "ERROR" if 'malicious' in item.lower() else "WARNING"
        else:
            return "INFO"
    
    def get_description(self, category: str, item: str) -> str:
        """Generate description for specific findings"""
        descriptions = {
            "packer": f"Application code is packed with {item}. This makes analysis more difficult and is often used to hide malicious behavior.",
            "compiler": f"Application was compiled with {item}.",
            "obfuscator": f"Application code is obfuscated with {item}, making analysis more difficult.",
            "abnormality": f"Abnormal code pattern detected: {item}. This may indicate tampering or malicious behavior.",
            "anti_vm": f"Anti-VM technique detected: {item}. The app may be attempting to detect if it's running in an analysis environment.",
            "anti_disassembly": f"Anti-disassembly technique detected: {item}. The app is using techniques to make reverse engineering more difficult.",
            "manipulator": f"Code manipulation detected: {item}. The app has been modified potentially to hide its behavior.",
            "protector": f"Application is using protection mechanism: {item}. This makes analysis more difficult."
        }
        
        return descriptions.get(category, f"{category}: {item}")


if __name__ == "__main__":
    module = APKiDModule()
    asyncio.run(module.start())