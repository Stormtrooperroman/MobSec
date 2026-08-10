import json
import os
import asyncio
import logging
from typing import Dict, Any, List
import zipfile
from mobsec_modules_library.static.static_module import StaticModule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class TruffleHogModule(StaticModule):
    def __init__(self):
        super().__init__("trufflehog_module")

    async def scan_files(self, file_path: str) -> List[Dict]:
        """Scan files using TruffleHog"""
        findings = []
        try:
            cmd = ["trufflehog", "filesystem", "--json", "--no-update", file_path]

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()
            logger.info(f"TruffleHog output: {stdout.decode()}")

            if stdout:
                for line in stdout.decode().splitlines():
                    try:
                        result = json.loads(line)
                        source_data = (
                            result.get("SourceMetadata", {})
                            .get("Data", {})
                            .get("Filesystem", {})
                        )
                        file_name = source_data.get("file", "")
                        line_number = source_data.get("line", 0)

                        raw_secret = result.get("Raw", "No raw value available")

                        finding = {
                            "rule_id": "secret_detection",
                            "name": f"Found {result.get('DetectorName', 'Unknown')} Secret",
                            "severity": "ERROR",
                            "location": {
                                "file": os.path.basename(file_name),
                                "line": line_number,
                                "path": file_name,
                            },
                            "metadata": {
                                "description": f"Detected {result.get('DetectorName', 'unknown')} secret pattern",
                                "detector": result.get("DetectorName", ""),
                                "entropy": result.get("Entropy", 0),
                                "category": "secret",
                                "secret_value": raw_secret,
                                "detector_type": result.get("DetectorType", ""),
                                "verified": result.get("Verified", False),
                                "extra_data": result.get("ExtraData", {}),
                            },
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
        file_path = os.path.join(
            "/shared_data", task_data["folder_path"], task_data["file_name"]
        )
        logger.info(f"Processing task for file: {file_path}")
        if not os.path.exists(file_path):
            return {"status": "error", "error": f"File not found: {file_path}"}

        try:
            findings = await self.scan_files(file_path)

            return {"status": "success", "results": findings}

        except Exception as e:
            logger.error(f"Error processing file: {str(e)}")
            return {"status": "error", "error": str(e)}


if __name__ == "__main__":
    module = TruffleHogModule()
    asyncio.run(module.start())
