# Writing Static Modules

This guide explains how to create static analysis modules for the Mobile Security Testing Platform. Static modules process APK/IPA files and source code asynchronously through Redis queues.

## Module Architecture

```
modules/
└── {module_name}/
    ├── Dockerfile              # Container configuration
    ├── config.yaml             # Module metadata
    ├── ...
    └── {ModuleName}Report.vue  # Optional: custom UI component
```

## Essential Files

### 1. config.yaml

This file defines your module's metadata:

```yaml
name: your_module_name
version: 0.1
description: A clear description of what your module does
author: your_name
# Optional: if false, disables autorun on startup. Default: true.
active: true
```

### 2. requirements.txt

List Python dependencies. If using the library:

```
mobsec-modules-library>=0.0.1
# Your specific dependencies
```

### 3. Dockerfile

Set up your module's environment:

```dockerfile
FROM python:3.9-slim

WORKDIR /module

# Install system dependencies
RUN apt-get update && apt-get install -y \
    your-analysis-tool \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Copy module files
COPY {module_name}_scan.py /module/
COPY config.yaml /module/


ENV REDIS_URL=redis://redis:6379

CMD ["python3", "{module_name}_scan.py"]
```

## Redis Integration

### Queue Structure

All modules communicate through Redis using this key structure:
- Module queue: `module:{module_name}:queue`
- Task data: `task:{task_id}`
- Result: `result:{module_name}:{file_hash}`

### Task Data Format

Tasks are stored in Redis with this structure:

```json
{
    "task_id": "uuid4-generated-id",
    "file_hash": "hash-of-the-file",
    "file_name": "example.apk",
    "file_type": "apk|ipa|source",
    "folder_path": "example-hash-of-the-file",
    "chain_task_id": "optional-chain-task-id",
    "module_name": "your_module_name"
}
```

### Shared Data Access

Files are available in the `/shared_data` directory:

```python
import os

base_path = os.path.join("/shared_data", task_data["folder_path"])

# For decompiled APKs (after JADX module runs)
code_dir = os.path.join(base_path, "source_code")

# For original files
file_path = os.path.join(base_path, task_data["file_name"])
```

## Results Format

All modules must return results in this standardized format:

### Successful Analysis

```json
{
    "status": "success",
    "results": {
        "findings": [
            {
                "rule_id": "unique_identifier",
                "name": "Finding Name",
                "severity": "HIGH|MEDIUM|LOW",
                "location": {
                    "file": "path/to/file.java",
                    "type": "java|kotlin|smali",
                    "line": 42,
                    "column": 10
                },
                "metadata": {
                    "description": "Detailed description",
                    "category": "security_issue",
                    "cwe": "CWE-123"
                }
            }
        ],
        "summary": {
            "total_findings": 1,
            "by_severity": {
                "HIGH": 1,
                "MEDIUM": 0,
                "LOW": 0
            }
        }
    }
}
```

### Error Response

```json
{
    "status": "error",
    "error": "Detailed error message"
}
```

## Implementation Without Library

If you prefer to implement the module without using the python library, handle the Redis loop manually:

```python
import json
import os
import asyncio
import redis
import logging
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MyModule:
    def __init__(self, module_name: str):
        self.redis_client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://redis:6379"),
            decode_responses=True
        )
        self.module_name = module_name

    async def start(self):
        """Main processing loop."""
        logger.info(f"Starting {self.module_name} module...")
        while True:
            try:
                # Get task from queue
                queue_key = f"module:{self.module_name}:queue"
                task_id = self.redis_client.lpop(queue_key)

                if task_id:
                    try:
                        # Get task data
                        task_data_str = self.redis_client.get(f"task:{task_id}")
                        if not task_data_str:
                            logger.error(f"Task data not found for {task_id}")
                            continue

                        task_data = json.loads(task_data_str)
                        logger.info(f"Processing {task_id}")

                        # Process the task
                        result = await self.process(task_data)

                        # Store result
                        result_key = f"result:{self.module_name}:{task_data['file_hash']}"
                        self.redis_client.set(result_key, json.dumps(result))
                        logger.info(f"Stored result for {task_id}")

                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse task data: {str(e)}")
                    except Exception as e:
                        logger.error(f"Error processing task {task_id}: {str(e)}")

                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Critical error: {str(e)}")
                await asyncio.sleep(5)

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Override this method to implement your analysis logic."""
        raise NotImplementedError("Subclasses must implement process()")

if __name__ == "__main__":
    module = MyModule("your_module_name")
    asyncio.run(module.start())
```

Then implement your specific module:

```python
import json
import os
import asyncio
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class SecurityScanModule(MyModule):
    def __init__(self):
        super().__init__("security_scan_module")

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Scan source code for security issues."""
        try:
            base_path = os.path.join("/shared_data", task_data["folder_path"])
            code_dir = os.path.join(base_path, "source_code")

            if not os.path.exists(code_dir):
                return {
                    "status": "error",
                    "error": "Source code not found"
                }

            logger.info(f"Scanning {code_dir}")

            # Run your analysis tool
            raw_results = await self._run_scan_tool(code_dir)

            if raw_results is None:
                return {
                    "status": "error",
                    "error": "Scan tool failed"
                }

            # Process and standardize results
            findings = self._process_findings(raw_results)
            summary = self._summarize_findings(findings)

            return {
                "status": "success",
                "results": {
                    "findings": findings,
                    "summary": summary
                }
            }

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _run_scan_tool(self, code_dir: str) -> Dict:
        """Execute analysis tool."""
        try:
            process = await asyncio.create_subprocess_exec(
                "your-scan-tool",
                "--output=json",
                code_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Tool error: {stderr.decode()}")
                return None

            return json.loads(stdout.decode())

        except Exception as e:
            logger.error(f"Failed to run scan tool: {str(e)}")
            return None

    def _process_findings(self, raw_results: Dict) -> List[Dict]:
        """Transform tool output into standardized findings."""
        findings = []

        for item in raw_results.get("issues", []):
            finding = {
                "rule_id": item.get("rule_id"),
                "name": item.get("title"),
                "severity": self._map_severity(item.get("severity")),
                "location": {
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "column": item.get("column", 0)
                },
                "metadata": {
                    "description": item.get("description"),
                    "category": item.get("category"),
                    "cwe": item.get("cwe"),
                }
            }
            findings.append(finding)

        return findings

    def _map_severity(self, level: str) -> str:
        """Map tool severity levels to standard levels."""
        mapping = {
            "critical": "HIGH",
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW",
            "info": "LOW"
        }
        return mapping.get(level, "MEDIUM")

    def _summarize_findings(self, findings: List[Dict]) -> Dict:
        """Generate summary statistics."""
        summary = {
            "total_findings": len(findings),
            "by_severity": {
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0
            }
        }

        for finding in findings:
            severity = finding.get("severity", "MEDIUM")
            if severity in summary["by_severity"]:
                summary["by_severity"][severity] += 1

        return summary

if __name__ == "__main__":
    module = SecurityScanModule()
    asyncio.run(module.start())
```

## Implementation with mobsec_modules_library

The library provides a `StaticModule` base class that handles the Redis loop automatically:

### 1. Basic Structure

Inherit from `StaticModule`:

```python
from mobsec_modules_library.static import StaticModule
from typing import Dict, Any
import asyncio

class YourAnalysisModule(StaticModule):
    def __init__(self):
        super().__init__("your_module_name")

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a task and return standardized results."""
        try:
            # Your analysis logic here
            result = await self._run_analysis(task_data)
            return result
        except Exception as e:
            logger.error(f"Error processing task: {str(e)}")
            return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    module = YourAnalysisModule()
    asyncio.run(module.start())
```

### 2. Complete Example with Library

```python
import json
import os
import asyncio
from typing import Dict, Any, List
import logging
from mobsec_modules_library.static import StaticModule

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SecurityScanModule(StaticModule):
    def __init__(self):
        super().__init__("security_scan_module")

    async def process(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Scan source code for security issues."""
        try:
            base_path = os.path.join("/shared_data", task_data["folder_path"])
            code_dir = os.path.join(base_path, "source_code")

            if not os.path.exists(code_dir):
                return {
                    "status": "error",
                    "error": "Source code not found"
                }

            logger.info(f"Scanning {code_dir}")

            # Run your analysis tool
            raw_results = await self._run_scan_tool(code_dir)

            if raw_results is None:
                return {
                    "status": "error",
                    "error": "Scan tool failed"
                }

            # Process and standardize results
            findings = self._process_findings(raw_results)
            summary = self._summarize_findings(findings)

            return {
                "status": "success",
                "results": {
                    "findings": findings,
                    "summary": summary
                }
            }

        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _run_scan_tool(self, code_dir: str) -> Dict:
        """Execute analysis tool."""
        try:
            process = await asyncio.create_subprocess_exec(
                "your-scan-tool",
                "--output=json",
                "--strict",
                code_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Tool error: {stderr.decode()}")
                return None

            return json.loads(stdout.decode())

        except Exception as e:
            logger.error(f"Failed to run scan tool: {str(e)}")
            return None

    def _process_findings(self, raw_results: Dict) -> List[Dict]:
        """Transform tool output into standardized findings."""
        findings = []

        for item in raw_results.get("issues", []):
            finding = {
                "rule_id": item.get("rule_id"),
                "name": item.get("title"),
                "severity": self._map_severity(item.get("severity")),
                "location": {
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "column": item.get("column", 0)
                },
                "metadata": {
                    "description": item.get("description"),
                    "category": item.get("category"),
                    "cwe": item.get("cwe"),
                }
            }
            findings.append(finding)

        return findings

    def _map_severity(self, level: str) -> str:
        """Map tool severity levels to standard levels."""
        mapping = {
            "critical": "HIGH",
            "high": "HIGH",
            "medium": "MEDIUM",
            "low": "LOW",
            "info": "LOW"
        }
        return mapping.get(level, "MEDIUM")

    def _summarize_findings(self, findings: List[Dict]) -> Dict:
        """Generate summary statistics."""
        summary = {
            "total_findings": len(findings),
            "by_severity": {
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0
            }
        }

        for finding in findings:
            severity = finding.get("severity", "MEDIUM")
            if severity in summary["by_severity"]:
                summary["by_severity"][severity] += 1

        return summary

if __name__ == "__main__":
    module = SecurityScanModule()
    asyncio.run(module.start())
```

## Custom UI Components

Create a Vue component to visualize your module's results. Name it `{ModuleName}Report.vue` and place it in your module's root directory:

```vue
<template>
  <div class="security-scan-report">
    <!-- Empty State -->
    <div v-if="!hasResults" class="module-empty">
      <div class="empty-icon">🔍</div>
      <h3>Security Scan Results</h3>
      <p>No results available.</p>
    </div>

    <!-- Results Display -->
    <div v-else class="module-results">
      <div class="summary-section">
        <h3>Summary</h3>
        <div class="summary-stats">
          <div class="stat">
            <span class="label">Total Findings:</span>
            <span class="value">{{ totalFindings }}</span>
          </div>
          <div class="stat">
            <span class="label high">HIGH:</span>
            <span class="count">{{ findingsByLevel.HIGH }}</span>
          </div>
          <div class="stat">
            <span class="label medium">MEDIUM:</span>
            <span class="count">{{ findingsByLevel.MEDIUM }}</span>
          </div>
          <div class="stat">
            <span class="label low">LOW:</span>
            <span class="count">{{ findingsByLevel.LOW }}</span>
          </div>
        </div>
      </div>

      <div class="findings-section">
        <h3>Findings</h3>
        <div v-for="finding in processedResults" :key="finding.rule_id" class="finding-card">
          <div class="finding-header">
            <span class="severity" :class="finding.severity.toLowerCase()">
              {{ finding.severity }}
            </span>
            <h4 class="finding-title">{{ finding.name }}</h4>
          </div>
          <p class="description">{{ finding.metadata.description }}</p>
          <div class="location">
            <span class="file">{{ finding.location.file }}</span>
            <span v-if="finding.location.line" class="line">:{{ finding.location.line }}</span>
          </div>
          <div v-if="finding.metadata.cwe" class="metadata">
            <span class="cwe">{{ finding.metadata.cwe }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'SecurityScanReport',
  props: {
    moduleData: {
      type: Object,
      required: true
    }
  },
  computed: {
    hasResults() {
      return !!this.moduleData?.results;
    },
    processedResults() {
      return this.moduleData?.results?.findings || [];
    },
    totalFindings() {
      return this.processedResults.length;
    },
    findingsByLevel() {
      const levels = { HIGH: 0, MEDIUM: 0, LOW: 0 };
      for (const finding of this.processedResults) {
        const level = finding.severity || 'MEDIUM';
        if (level in levels) levels[level]++;
      }
      return levels;
    }
  }
}
</script>

<style scoped>
.module-empty {
  text-align: center;
  padding: 40px 20px;
  color: #999;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 10px;
}

.summary-stats {
  display: flex;
  gap: 20px;
  margin: 15px 0;
}

.stat {
  display: flex;
  gap: 8px;
  align-items: center;
}

.stat .label {
  font-weight: 500;
}

.stat .label.high { color: #c62828; }
.stat .label.medium { color: #e65100; }
.stat .label.low { color: #2e7d32; }

.stat .count {
  font-weight: bold;
  font-size: 18px;
}

.finding-card {
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 15px;
  margin-bottom: 12px;
}

.finding-header {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}

.severity {
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: bold;
  text-transform: uppercase;
  min-width: 60px;
  text-align: center;
}

.severity.high {
  background-color: #ffebee;
  color: #c62828;
}

.severity.medium {
  background-color: #fff3e0;
  color: #e65100;
}

.severity.low {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.finding-title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.description {
  margin: 8px 0;
  color: #555;
  font-size: 13px;
}

.location {
  font-size: 12px;
  color: #999;
  font-family: monospace;
  margin: 8px 0;
}

.metadata {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.cwe {
  background-color: #f5f5f5;
  padding: 2px 6px;
  border-radius: 2px;
  font-size: 11px;
  font-family: monospace;
}
</style>
```

### Component Registration

Your component will be automatically registered if it follows these rules:
1. Named as `{ModuleName}Report.vue`
2. Placed in the module's root directory
3. Exports a default Vue component

## Further Resources

- [mobsec_modules_library GitHub](https://github.com/Stormtrooperroman/mobsec_modules_library)
- View example modules: Semgrep, Permissions, JADX in `/modules/` directory
