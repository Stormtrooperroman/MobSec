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
           // Contents of config.yaml
       },
       "healthcheck_url": "your-module-base-url/health"
   }
   ```

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
