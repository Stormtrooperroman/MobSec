# Writing Dynamic Modules

This guide explains how to create interactive dynamic testing modules for the Mobile Security Testing Platform. Dynamic modules handle real-time device communication through WebSocket connections with the frontend UI.

## Overview

Dynamic modules enable interactive testing sessions where:
- Users interact with mobile devices in real time (Android only for now).
- WebSocket connections maintain persistent state
- Frontend UI can send commands and receive live updates
- Complex workflows like instrumentation, interception, and debugging are supported


## Module Architecture

```
modules/
└── {module_name}/
    ├── Dockerfile                     # Container configuration
    ├── config.yaml                    # Module metadata
    ├── ...
    └── {ModuleName}Tool.vue           # Frontend UI component (optional)
```

## Essential Files

### 1. config.yaml

```yaml
name: your_dynamic_module
version: 0.1
description: A clear description of what your module does
author: your_name
type: dynamic 
port: 8090                  # Port the module listens on
map_name: your_tool         # WebSocket route identifier used by proxy to route messages
view:
  icon: bug                 # Font Awesome icon name displayed in frontend UI
  title: Your Tool          # Display title in the UI
# Optional: if false, disables autorun on startup. Default: true.
active: true
```

### 2. requirements.txt

If using the library:

```
mobsec-modules-library>=0.0.1
# Your tool dependencies
```


### 3. Dockerfile

```dockerfile
FROM python:3.9-slim

WORKDIR /module

# Install system dependencies
RUN apt-get update && apt-get install -y \
    adb \
    # Your tool dependencies
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt ./
RUN pip3 install -r requirements.txt

# Copy module code
COPY *.py /module/
COPY config.yaml /module/

ENV PORT=8090

CMD ["python3", "{module_name}_server.py"]
```

## WebSocket Communication Protocol

All dynamic modules communicate with the frontend via WebSocket using JSON messages.

### Message Format

**Frontend → Backend:**
```json
{
    "action": "command_name",
    "params": {
        "key": "value"
    }
}
```

**Backend → Frontend:**
```json
{
    "type": "module_name",
    "action": "response_type",
    "result": {}
}
```


## Implementation Without Library

Implement WebSocket server manually, for example, using FastAPI:

```python
import json
import logging
import asyncio
from typing import Dict, Any, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class YourToolManager:
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.is_running = False
        self.tool_session = None

    async def start(self) -> bool:
        """Initialize the module for the device."""
        try:
            self.is_running = True
            logger.info(f"Starting for device {self.device_id}")

            # Get device information
            device_info = await self._get_device_info()

            # Initialize your tool
            self.tool_session = await self._initialize_tool()

            # Send ready signal to frontend
            await self.send_response({
                "type": "your_tool",
                "action": "ready",
                "device_info": device_info,
                "status": "initialized"
            })

            return True

        except Exception as e:
            logger.error(f"Failed to start: {str(e)}")
            await self.send_error(str(e))
            return False

    async def handle_message(self, text: str) -> None:
        """Process incoming messages from the frontend."""
        try:
            data = json.loads(text)
            action = data.get("action")
            params = data.get("params", {})

            if action == "execute_command":
                result = await self._execute_command(params)
                await self.send_response({
                    "type": "your_tool",
                    "action": "command_result",
                    "result": result
                })

            elif action == "get_status":
                status = await self._get_status()
                await self.send_response({
                    "type": "your_tool",
                    "action": "status",
                    "status": status
                })

            else:
                await self.send_error(f"Unknown action: {action}")

        except json.JSONDecodeError as e:
            await self.send_error(f"Invalid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_error(str(e))

    async def stop(self) -> None:
        """Cleanup when WebSocket closes."""
        if self.is_running:
            try:
                await self._cleanup_tool()
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
            finally:
                self.is_running = False

    async def send_response(self, data: Dict[str, Any]) -> None:
        """Send JSON response to frontend."""
        try:
            await self.websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")

    async def send_error(self, message: str) -> None:
        """Send error message to frontend."""
        await self.send_response({
            "type": "your_tool",
            "action": "error",
            "message": message
        })

    # Tool-specific methods (override these)

    async def _get_device_info(self) -> Dict[str, Any]:
        """Retrieve device information."""
        return {"sdk": "unknown", "arch": "unknown", "rooted": False}

    async def _initialize_tool(self) -> Any:
        """Initialize your analysis tool."""
        return {}

    async def _execute_command(self, params: Dict) -> Dict:
        """Execute a user command."""
        return {"status": "success"}

    async def _get_status(self) -> Dict:
        """Get current tool status."""
        return {"is_running": self.is_running, "device_id": self.device_id}

    async def _cleanup_tool(self) -> None:
        """Clean up tool resources."""
        if self.tool_session:
            pass


# Create FastAPI app and WebSocket endpoint
app = FastAPI(title="Your Module")

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected for device {device_id}")

    manager = YourToolManager(websocket, device_id)
    if not await manager.start():
        await websocket.close(code=4000, reason="Failed to start manager")
        return

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive" and "text" in message:
                await manager.handle_message(message["text"])
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        await manager.stop()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

## Device Communication

Use `adb` commands to interact with the device. Example helper functions:

```python
import subprocess
import asyncio

async def execute_adb_shell(device_id: str, cmd: str) -> str:
    """Execute shell command on device."""
    try:
        process = await asyncio.create_subprocess_exec(
            "adb", "-s", device_id, "shell", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(stderr.decode())
        return stdout.decode()
    except Exception as e:
        logger.error(f"ADB error: {str(e)}")
        raise

async def execute_adb_command(device_id: str, args: list) -> str:
    """Execute ADB command."""
    try:
        process = await asyncio.create_subprocess_exec(
            "adb", "-s", device_id, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(stderr.decode())
        return stdout.decode()
    except Exception as e:
        logger.error(f"ADB error: {str(e)}")
        raise
```

## Complete Example Without Library

Here's a full interactive tool module without the library:

```python
import json
import logging
import asyncio
import os
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class InteractiveToolManager:
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.is_running = False
        self.current_process = None

    async def start(self) -> bool:
        try:
            self.is_running = True

            # Get device info
            device_info = await self._get_device_info()

            await self.send_response({
                "type": "interactive_tool",
                "action": "ready",
                "device_info": device_info
            })

            return True
        except Exception as e:
            logger.error(f"Start error: {str(e)}")
            return False

    async def handle_message(self, text: str) -> None:
        try:
            data = json.loads(text)
            action = data.get("action")
            params = data.get("params", {})

            if action == "attach":
                result = await self._attach_app(params.get("package"))
                await self.send_response({
                    "type": "interactive_tool",
                    "action": "attached",
                    "result": result
                })

            elif action == "detach":
                await self._detach_app()
                await self.send_response({
                    "type": "interactive_tool",
                    "action": "detached"
                })

            elif action == "send_command":
                result = await self._send_command(params.get("command"))
                await self.send_response({
                    "type": "interactive_tool",
                    "action": "command_response",
                    "result": result
                })

            else:
                await self.send_error(f"Unknown action: {action}")

        except Exception as e:
            await self.send_error(str(e))

    async def stop(self) -> None:
        if self.is_running:
            await self._detach_app()
            self.is_running = False

    async def _get_device_info(self) -> Dict:
        try:
            version = await self._adb_shell("getprop ro.build.version.release")
            model = await self._adb_shell("getprop ro.product.model")

            return {
                "version": version.strip(),
                "model": model.strip()
            }
        except Exception as e:
            logger.error(f"Error getting device info: {str(e)}")
            return {}

    async def _attach_app(self, package: str) -> Dict:
        """Attach to an application."""
        try:
            await self._adb_shell(f"monkey -p {package} 1")
            await asyncio.sleep(1)
            return {"status": "success", "package": package}
        except Exception as e:
            logger.error(f"Attach failed: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def _detach_app(self) -> None:
        """Detach from current app."""
        if self.current_process:
            self.current_process = None

    async def _send_command(self, command: str) -> Dict:
        """Execute a command."""
        try:
            result = await self._adb_shell(command)
            return {"status": "success", "output": result.strip()}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _adb_shell(self, cmd: str) -> str:
        """Execute ADB shell command."""
        process = await asyncio.create_subprocess_exec(
            "adb", "-s", self.device_id, "shell", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise Exception(stderr.decode())
        return stdout.decode()

    async def send_response(self, data: Dict[str, Any]) -> None:
        """Send response to frontend."""
        try:
            await self.websocket.send_text(json.dumps(data))
        except Exception as e:
            logger.error(f"Send error: {str(e)}")

    async def send_error(self, message: str) -> None:
        """Send error to frontend."""
        await self.send_response({
            "type": "interactive_tool",
            "action": "error",
            "message": message
        })

# FastAPI setup
app = FastAPI(title="Interactive Tool Module")

@app.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connected for device {device_id}")

    manager = InteractiveToolManager(websocket, device_id)
    if not await manager.start():
        await websocket.close(code=4000, reason="Failed to start manager")
        return

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if message["type"] == "websocket.receive" and "text" in message:
                await manager.handle_message(message["text"])
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        await manager.stop()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

## Implementation with mobsec_modules_library

The library provides `BaseModuleManager` and `create_module_app` to handle boilerplate WebSocket management and ADB utilities.

### 1. Create the Manager

Inherit from `BaseModuleManager`:

```python
import json
import logging
from typing import Dict, Any
from fastapi import WebSocket
from mobsec_modules_library.dynamic import BaseModuleManager
from mobsec_modules_library.dynamic.adb_utils import (
    execute_adb_shell,
    check_su_availability,
)

logger = logging.getLogger(__name__)

class YourToolManager(BaseModuleManager):
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.is_running = False
        self.tool_session = None

    async def start(self) -> bool:
        """Initialize the module for the device."""
        try:
            self.is_running = True
            logger.info(f"Starting for device {self.device_id}")

            # Get device information
            device_info = await self._get_device_info()

            # Initialize your tool
            self.tool_session = await self._initialize_tool()

            # Send ready signal to frontend
            await self.send_response({
                "type": "your_tool",
                "action": "ready",
                "device_info": device_info,
                "status": "initialized"
            })

            return True

        except Exception as e:
            logger.error(f"Failed to start: {str(e)}")
            await self.send_error(str(e))
            return False

    async def handle_message(
        self, websocket: WebSocket, device_id: str, text: str
    ) -> None:
        """Process incoming messages from the frontend."""
        try:
            data = json.loads(text)
            action = data.get("action")
            params = data.get("params", {})

            if action == "execute_command":
                result = await self._execute_command(params)
                await self.send_response({
                    "type": "your_tool",
                    "action": "command_result",
                    "result": result
                })

            elif action == "get_status":
                status = await self._get_status()
                await self.send_response({
                    "type": "your_tool",
                    "action": "status",
                    "status": status
                })

            else:
                await self.send_error(f"Unknown action: {action}")

        except json.JSONDecodeError as e:
            await self.send_error(f"Invalid JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling message: {str(e)}")
            await self.send_error(str(e))

    async def stop(self) -> None:
        """Cleanup when WebSocket closes."""
        if self.is_running:
            try:
                await self._cleanup_tool()
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
            finally:
                self.is_running = False

    async def _get_device_info(self) -> Dict[str, Any]:
        """Retrieve device information."""
        try:
            sdk = await execute_adb_shell(
                self.device_id,
                "getprop ro.build.version.sdk"
            )
            arch = await execute_adb_shell(
                self.device_id,
                "getprop ro.product.cpu.abi"
            )
            has_root = await check_su_availability(self.device_id)

            return {
                "sdk": sdk.strip(),
                "arch": arch.strip(),
                "rooted": has_root
            }
        except Exception as e:
            logger.error(f"Error getting device info: {str(e)}")
            return {}

    async def _initialize_tool(self) -> Any:
        """Initialize your analysis tool."""
        return {}

    async def _execute_command(self, params: Dict) -> Dict:
        """Execute a user command."""
        return {"status": "success"}

    async def _get_status(self) -> Dict:
        """Get current tool status."""
        return {
            "is_running": self.is_running,
            "device_id": self.device_id
        }

    async def _cleanup_tool(self) -> None:
        """Clean up tool resources."""
        if self.tool_session:
            pass
```

### 2. Create the Server

Use `create_module_app` from the library:

```python
import logging
from fastapi import WebSocket
from mobsec_modules_library.dynamic import (
    BaseModuleManager,
    create_module_app,
    run_module_server,
)
from {module_name}_manager import YourToolManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

class YourModuleManager(BaseModuleManager):
    """Wrapper that implements BaseModuleManager interface."""

    def __init__(self, websocket: WebSocket, device_id: str):
        self._manager = YourToolManager(websocket, device_id)

    async def start(self) -> bool:
        return await self._manager.start()

    async def handle_message(
        self, websocket: WebSocket, device_id: str, text: str
    ) -> None:
        await self._manager.handle_message(websocket, device_id, text)

    async def stop(self) -> None:
        await self._manager.stop()

async def manager_factory(
    websocket: WebSocket, device_id: str
) -> YourModuleManager:
    """Factory function for creating managers."""
    return YourModuleManager(websocket, device_id)

# Create the FastAPI app with WebSocket support
app = create_module_app("Your Module", manager_factory)

if __name__ == "__main__":
    run_module_server(app, default_port=8090)
```

## ADB Utilities (Library)

When using the library, use these utilities:

```python
from mobsec_modules_library.dynamic.adb_utils import (
    execute_adb_command,       # Run ADB command
    execute_adb_shell,         # Run shell command on device
    check_su_availability,     # Check for root access
    remove_all_port_forwarding,# Clean up port forwarding
)

# Execute shell command
output = await execute_adb_shell(device_id, "pm list packages -3")

# Set up port forwarding
await execute_adb_command(device_id, ["forward", "tcp:8000", "tcp:8000"])

# Check for root
has_root = await check_su_availability(device_id)

# Clean up forwarding on disconnect
await remove_all_port_forwarding(device_id)
```

## Frontend UI Component

Create a Vue component for user interaction. Name it `{ModuleName}Tool.vue`:

```vue
<template>
  <div class="interactive-tool">
    <!-- Connection Status -->
    <div class="status-bar" :class="connected ? 'connected' : 'disconnected'">
      <span class="status-indicator"></span>
      <span>{{ connected ? 'Connected' : 'Disconnected' }}</span>
      <span v-if="deviceInfo" class="device-name">{{ deviceInfo.model }}</span>
    </div>

    <!-- Main Content -->
    <div class="tool-content">
      <!-- App Selector -->
      <div class="control-panel">
        <div class="control-group">
          <label>Package:</label>
          <input v-model="selectedPackage" type="text" placeholder="com.example.app">
          <button @click="attachApp" :disabled="!connected">Attach</button>
          <button @click="detachApp" :disabled="!connected || !attached">Detach</button>
        </div>
      </div>

      <!-- Console/Output -->
      <div class="console">
        <div class="console-header">Output</div>
        <div class="console-content">
          <div v-for="(line, idx) in consoleLogs" :key="idx" class="console-line">
            {{ line }}
          </div>
        </div>
      </div>

      <!-- Command Input -->
      <div class="command-input">
        <input 
          v-model="commandInput"
          @keyup.enter="sendCommand"
          type="text"
          placeholder="Enter command..."
        >
        <button @click="sendCommand" :disabled="!attached">Send</button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: 'InteractiveToolComponent',
  data() {
    return {
      ws: null,
      connected: false,
      attached: false,
      selectedPackage: '',
      commandInput: '',
      consoleLogs: [],
      deviceInfo: null
    }
  },
  mounted() {
    this.connectWebSocket()
  },
  beforeUnmount() {
    if (this.ws) {
      this.ws.close()
    }
  },
  methods: {
    connectWebSocket() {
      const deviceId = this.$route.params.deviceId || 'device'
      this.ws = new WebSocket(`ws://localhost:8090/ws/${deviceId}`)

      this.ws.onopen = () => {
        this.connected = true
        this.addLog('Connected to device')
      }

      this.ws.onmessage = (event) => {
        const data = JSON.parse(event.data)

        if (data.action === 'ready') {
          this.deviceInfo = data.device_info
          this.addLog(`Device ready: ${data.device_info.model}`)
        }

        if (data.action === 'attached') {
          this.attached = true
          this.addLog(`Attached to ${data.result.package}`)
        }

        if (data.action === 'detached') {
          this.attached = false
          this.addLog('Detached')
        }

        if (data.action === 'command_response') {
          this.addLog(data.result.output)
        }

        if (data.action === 'error') {
          this.addLog(`ERROR: ${data.message}`)
        }
      }

      this.ws.onerror = (event) => {
        this.addLog(`WebSocket error: ${event}`)
      }

      this.ws.onclose = () => {
        this.connected = false
        this.attached = false
        this.addLog('Disconnected')
      }
    },
    attachApp() {
      this.ws.send(JSON.stringify({
        action: 'attach',
        params: { package: this.selectedPackage }
      }))
    },
    detachApp() {
      this.ws.send(JSON.stringify({
        action: 'detach'
      }))
    },
    sendCommand() {
      if (!this.commandInput) return

      this.addLog(`> ${this.commandInput}`)

      this.ws.send(JSON.stringify({
        action: 'send_command',
        params: { command: this.commandInput }
      }))

      this.commandInput = ''
    },
    addLog(message) {
      this.consoleLogs.push(message)
      this.$nextTick(() => {
        const console = this.$el.querySelector('.console-content')
        if (console) {
          console.scrollTop = console.scrollHeight
        }
      })
    }
  }
}
</script>

<style scoped>
.interactive-tool {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 20px;
}

.status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 4px;
  margin-bottom: 20px;
  font-weight: 500;
}

.status-bar.connected {
  background-color: #e8f5e9;
  color: #2e7d32;
}

.status-bar.disconnected {
  background-color: #ffebee;
  color: #c62828;
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: currentColor;
}

.control-panel {
  margin-bottom: 20px;
  padding: 15px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}

.control-group {
  display: flex;
  gap: 10px;
  align-items: center;
}

.console {
  flex: 1;
  margin-bottom: 20px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
}

.console-header {
  background-color: #f5f5f5;
  padding: 10px;
  border-bottom: 1px solid #e0e0e0;
  font-weight: 500;
}

.console-content {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  font-family: monospace;
  font-size: 12px;
  background-color: #fafafa;
}

.console-line {
  line-height: 1.6;
  color: #333;
}

.command-input {
  display: flex;
  gap: 10px;
}

.command-input input {
  flex: 1;
  padding: 10px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-family: monospace;
  font-size: 13px;
}

.command-input button {
  padding: 10px 20px;
  background-color: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.command-input button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

button {
  padding: 8px 16px;
  background-color: #1976d2;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

button:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

input {
  padding: 8px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}
</style>
```

## Further Resources

- [mobsec_modules_library GitHub](https://github.com/Stormtrooperroman/mobsec_modules_library)
- View example modules: Frida, mitmproxy in `/modules/` directory
