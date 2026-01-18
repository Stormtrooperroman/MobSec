# Writing Your Own External Module

This guide explains how to create a custom external module for the Mobile Security Testing Platform. External modules can be written in any programming language and run on separate servers, communicating with the main platform via HTTP and Redis.

## Module Configuration

Each external module must have a `config.yaml` file that defines its metadata:

```yaml
name: "your-module-name"
version: "1.0.0"
description: "Clear description of what your module does"
author: "Your Name"
input_formats: 
  - "apk"
  - "ipa"
  - "source"
```

## Required Environment Variables

Your module should accept these environment variables:
- `MOBSEC_API_URL`: URL of the main platform API (e.g., "http://backend:8000/api/v1")
- `MODULE_ID`: Unique identifier for your module
- `MODULE_BASE_URL`: Base URL where your module is accessible
- `REDIS_URL`: URL for Redis connection

## Required API Endpoints

Your module must implement these HTTP endpoints:

### 1. Health Check
```
GET /health
```
Response:
```json
{
    "status": "healthy"
}
```

### 2. Process Operation
```
POST /operations/process
```
Request body:
```json
{
    "task_id": "uuid4-string",
    "file_hash": "sha256-hash",
    "chain_task_id": "optional-chain-task-id",
    "data": {
        "folder_path": "/path/to/files",
        "file_type": "apk",
        "platform": "android"
    }
}
```
Response:
```json
{
    "status": "success",
    "data": {
        "task_id": "uuid4-string",
        "message": "Task added to queue"
    }
}
```

### 3. UI Component (Optional)
```
GET /ui-component
```
This endpoint is optional and should be implemented if your module provides a custom Vue.js component for displaying results in the platform's UI.

Response:
```json
{
    "component_name": "YourModuleReport",
    "component_content": "<template>...</template><script>...</script><style>...</style>"
}
```

The `component_content` should contain the complete Vue.js component code (template, script, and style sections). The component will be dynamically loaded by the platform to display your module's results.

**Note**: If you implement this endpoint, you must also include UI component information in your module registration (see Module Registration section below).

## Communication Flow

1. **Module Registration**
   - On startup, module must register itself with the main platform:
   ```
   POST {MOBSEC_API_URL}/external-modules/register
   ```
   Request body:
   ```json
   {
       "module_id": "your-module-id",
       "base_url": "your-module-base-url",
       "config": {
           "name": "your-module-name",
           "version": "1.0.0",
           "description": "Clear description of what your module does",
           "input_formats": ["apk", "ipa", "source"],
           "has_custom_ui": true,
           "ui_component": {
               "name": "YourModuleReport",
               "endpoint": "your-module-base-url/ui-component"
           }
       },
       "healthcheck_url": "your-module-base-url/health",
       "status": "active"
   }
   ```
   
   **Note on Custom UI**: If your module implements the `/ui-component` endpoint, include `has_custom_ui: true` and the `ui_component` object in the config. The `ui_component.name` should match the component name returned by your `/ui-component` endpoint, and `ui_component.endpoint` should be the full URL to your UI component endpoint. If your module doesn't have a custom UI, omit the `has_custom_ui` and `ui_component` fields (or set `has_custom_ui: false`).

2. **File Access**
   - To access files for analysis:
   ```
   GET {MOBSEC_API_URL}/external-modules/{MODULE_ID}/files?file_ids=[file_hash]
   ```
   - Response will be a tar.gz archive containing the files

3. **Result Submission**
   - Submit analysis results:
   ```
   POST {MOBSEC_API_URL}/external-modules/{MODULE_ID}/results
   ```
   Request body:
   ```json
   {
       "task_id": "task-id",
       "file_hash": "file-hash",
       "results": {
           "status": "success",
           "findings": [
               {
                   "rule_id": "finding_type",
                   "name": "Finding Name",
                   "severity": "HIGH|MEDIUM|LOW",
                   "location": {
                       "file": "file_name",
                       "path": "full/path/to/file",
                       "start_line": 42,
                       "end_line": 42,
                       "code": "affected_code"
                   },
                   "metadata": {
                       "description": "Finding description",
                       "category": "issue_category",
                       "additional_info": {}
                   }
               }
           ]
       }
   }
   ```

## Redis Communication

Your module should monitor the Redis queue for new tasks:

1. **Task Queue Key**: `module:{MODULE_ID}:queue`
2. **Task Data Key**: `task:{task_id}`
3. **Result Key**: `result:{MODULE_ID}:{file_hash}`

When a task appears in the queue:
1. Get task ID from the queue using LPOP
2. Get task data from Redis using the task ID
3. Process the task
4. Store results in Redis and submit them via API

## Error Handling

For error cases, return results in this format:
```json
{
    "status": "error",
    "error": "Detailed error message",
    "results": {
        "findings": []
    }
}
```

## Example Repository

For a complete working example of an external module, you can refer to this repository:
[External Module Example](https://github.com/Stormtrooperroman/external_module_example)

This repository contains a practical implementation of a TruffleHog-based external module.
