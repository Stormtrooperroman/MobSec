import redis
import json
import os
import asyncio
from typing import Dict, Any, List
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

class SemgrepModule:
    def __init__(self):
        self.redis_client = redis.Redis.from_url(os.getenv('REDIS_URL'), decode_responses=True)
        self.module_name = "semgrep_module"
        
    async def start(self):
        logger.info("Starting Semgrep Analysis module...")
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
        base_path = os.path.join("/shared_data", task_data["folder_path"])
        code_dir = os.path.join(base_path, "source_code")
        
        if not os.path.exists(code_dir):
            return {
                "status": "error",
                "error": "Decompiled source code not found. Run JADX module first."
            }
        
        
        # Build semgrep command with specified rules
        process = await asyncio.create_subprocess_exec(
            'semgrep',
            '--metrics=off',
            '--no-rewrite-rule-ids',
            '-q',
            '--config', f"./rules",
            '--json',
            code_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        logger.info(stdout)
        logger.info(stderr)
        if process.returncode == 0:
            try:
                scan_results = json.loads(stdout.decode())
                
                # Process and summarize results
                summary = self.summarize_results(scan_results)
                findings = self.process_findings(scan_results.get('results', []))
                
                return {
                    "status": "success",
                    "results": {
                        "summary": summary,
                        "findings": findings,
                        "metrics": {
                            "total_findings": len(findings),
                            "scan_time": scan_results.get('time', {})
                        }
                    }
                }
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "error": f"Failed to parse Semgrep output: {str(e)}"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": f"Failed to process results: {str(e)}"
                }
        else:
            return {
                "status": "error",
                "error": stderr.decode()
            }

    def summarize_results(self, scan_results: Dict) -> Dict[str, Any]:
        findings = scan_results.get('results', [])
        severity_counts = {"ERROR": 0, "WARNING": 0, "INFO": 0}
        categories = {}
        
        for finding in findings:
            # Count by severity
            severity = finding.get('extra', {}).get('severity', 'WARNING')
            severity_counts[severity] += 1
            
            # Count by category/rule
            rule_id = finding.get('check_id', 'unknown')
            categories[rule_id] = categories.get(rule_id, 0) + 1
        
        return {
            "severity_counts": severity_counts,
            "category_counts": categories,
            "scanned_files": len(scan_results.get('paths', {}).get('scanned', [])),
        }

    def process_findings(self, findings: List[Dict]) -> List[Dict]:
        processed_findings = []
        
        for finding in findings:
            processed_finding = {
                "rule_id": finding.get('check_id'),
                "severity": finding.get('extra', {}).get('severity', 'WARNING'),
                "message": finding.get('extra', {}).get('message', ''),
                "location": {
                    "file": finding.get('path'),
                    "start_line": finding.get('start', {}).get('line'),
                    "end_line": finding.get('end', {}).get('line'),
                    "code": finding.get('extra', {}).get('lines', '')
                },
                "metadata": {
                    "category": finding.get('extra', {}).get('category', ''),
                    "technology": finding.get('extra', {}).get('technology', []),
                    "cwe": finding.get('extra', {}).get('cwe', []),
                    "owasp": finding.get('extra', {}).get('owasp', [])
                }
            }
            processed_findings.append(processed_finding)
            
        return processed_findings

if __name__ == "__main__":
    module = SemgrepModule()
    asyncio.run(module.start())