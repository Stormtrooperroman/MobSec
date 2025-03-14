# Writing Your Own Module

This guide explains how to create a custom module for the Mobile Security Testing Platform. Each module runs in a Docker container and communicates via Redis queues to process tasks.

## Module Structure

Each module should follow this Docker-based structure:

```
modules/
└── {module_name}/
    ├── Dockerfile          # Container configuration
    ├── ...
    └── config.yaml         # Module metadata
```

## Essential Files

### 1. config.yaml
This file defines your module's metadata:

```yaml
name: your_module_name
version: 0.1
description: A clear description of what your module does
author: your_name
```
Optional you can add `active: False` for disable autorun on startup.

### 2. Dockerfile
The Dockerfile sets up your module's environment. Here's an example from the semgrep module:

```dockerfile
FROM python:3.9-slim

WORKDIR /module

# Install required packages
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Copy module files
COPY semgrep_scan.py /module/
COPY config.yaml /module/
COPY rules /module/rules

CMD ["python3", "semgrep_scan.py"]
```

## Module Guidelines

### 1. Redis Integration

#### Queue Structure
- Module queue key: `module:{module_name}:queue`
- Task data key: `task:{task_id}`
- Result key: `result:{module_name}:{file_hash}`

#### Task Data Format
Tasks are stored in Redis with this structure:
```json
{
    "task_id": "uuid4-generated-id",
    "file_hash": "hash-of-the-file",
    "file_name": "example.apk",
    "file_type": "apk",
    "folder_path": "example-hash-of-the-file",
    "chain_task_id": "optional-chain-task-id",
    "module_name": "your_module_name"
}
```

#### Module Processing Loop
Example of processing loop using Python:
```python
async def start(self):
    while True:
        try:
            # Get task from queue
            task_id = self.redis_client.lpop(f"module:{self.module_name}:queue")
            
            if task_id:
                # Get task data
                task_data_str = self.redis_client.get(f"task:{task_id}")
                task_data = json.loads(task_data_str)
                
                # Process the task
                result = await self.process(task_data)
                
                # Store result
                result_key = f"result:{self.module_name}:{task_data['file_hash']}"
                self.redis_client.set(result_key, json.dumps(result))
            
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            await asyncio.sleep(5)
```

### 2. Results Format

Results must be stored in Redis in a standardized JSON format. Here are examples for different scenarios:

#### Successful Analysis
```json
{
    "status": "success",
    "results": [
        {
            "rule_id": "finding_type_1",
            "name": "Finding Name",
            "severity": "HIGH",
            "location": {
                "file": "path/to/file.java",
                "type": "java",
                "line": 42,
                "column": 10
            },
            "metadata": {
                "description": "Detailed description of the finding",
                "category": "security_issue",
                "cwe": "CWE-123",
                "additional_info": "Any extra information"
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
```

It could be other format in results if you use custom .vue file.

#### Error Case
```json
{
    "status": "error",
    "error": "Detailed error message"
}
```

#### Important Result Fields
- `status`: Required. Either "success" or "error"
- `results`: Array of findings (for success status)
- `error`: Error message (for error status)

#### Severity Levels
Use standardized severity levels:
- `ERROR` - Critical security issues
- `WARNING` - Potential security concerns
- `INFO` - Informational findings

### 3. Shared Data Access
   - Files are available in `/shared_data` directory
   - Use the provided file paths in task_data

### 4. Error Handling
   - Implement proper error handling
   - Log errors with appropriate levels
   - Return error status in results when needed



## Writing Custom Report Views

To create a custom visualization for your module's results, you can create a Vue component. Name your component file as `{ModuleName}Report.vue` and place it in your module's directory.

### Basic Structure

```vue
<template>
  <div class="your-module-report">
    <!-- Empty State -->
    <div v-if="!hasResults" class="module-empty">
      <div class="empty-icon">📊</div>
      <h3>Your Module Name</h3>
      <p>No results available.</p>
    </div>

    <!-- Results Display -->
    <div v-else class="module-results">
      <div class="module-header">
        <h3 class="module-title">Your Module Results</h3>
        <!-- Your visualization here -->
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'YourModuleReport',
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
    // Add more computed properties to process your results
    processedResults() {
      return this.moduleData?.results || [];
    }
  }
}
</script>
```

### Data Structure

Your component will receive the module results through the `moduleData` prop:

```javascript
props: {
  moduleData: {
    type: Object,
    required: true,
    // Example structure:
    // {
    //   status: "success",
    //   results: [...your findings...]
    // }
  }
}
```


### Component Registration

Your component will be automatically registered if it follows these rules:
1. Named as `{ModuleName}Report.vue`
2. Placed in the module's root directory
3. Exports a default Vue component

The platform will automatically detect and load your custom view when displaying module results.
