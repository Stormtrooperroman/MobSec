import asyncio
import json
import logging
import os
import socket
import tempfile
from typing import Any, Dict, List

import frida
from fastapi import WebSocket

from adb_utils import execute_adb_command, execute_adb_shell, remove_all_port_forwarding
from base_websocket_manager import BaseWebSocketManager
from frida_script_compiler import compile_script
from frida_script_service import FridaScriptService

logger = logging.getLogger(__name__)


class DeviceInfoHelper:
    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        try:
            parts = ip.split(".")
            if len(parts) != 4:
                return False
            for part in parts:
                if not 0 <= int(part) <= 255:
                    return False
            return True
        except (ValueError, AttributeError):
            return False


class FridaManager(BaseWebSocketManager):
    def __init__(self, websocket: WebSocket, device_id: str):
        super().__init__(websocket, "frida")
        self.device_id = device_id
        self.is_running = False

        self.device_arch = None
        self.frida_version = "17.7.3"
        self.frida_host = None
        self.frida_port = 27042
        self.device_ip = None

        self.frida_device = None
        self.frida_session = None
        self.frida_script = None
        self.current_script_name = None
        self.spawn_pid = None
        self.adb_forward_port = None

        self.script_service = FridaScriptService()

    def _get_frida_device_sync(self):
        if self.frida_host and self.frida_port:
            return frida.get_device_manager().add_remote_device(
                f"{self.frida_host}:{self.frida_port}"
            )
        return frida.get_usb_device()

    async def start(self):
        if self.is_running:
            return True

        try:
            self.is_running = True
            logger.info("Starting Frida manager for device %s", self.device_id)

            await self.get_device_ip()
            await self.detect_device_architecture()

            frida_installed = await self.check_frida_installation()
            frida_running = await self.check_frida_server_status()

            await self.send_response(
                {
                    "type": "frida",
                    "action": "ready",
                    "frida_installed": frida_installed,
                    "frida_running": frida_running,
                    "device_arch": self.device_arch,
                    "frida_version": self.frida_version,
                    "frida_host": self.frida_host,
                    "frida_port": self.frida_port,
                    "device_ip": self.device_ip,
                }
            )
            return True
        except Exception as e:
            logger.error("Error starting Frida manager: %s", str(e))
            self.is_running = False
            return False

    async def stop(self):
        if not self.is_running:
            return

        self.is_running = False
        await self._cleanup_frida_session()

        if self.frida_host == "localhost" and self.adb_forward_port:
            await self.remove_port_forwarding()

        logger.info("Frida manager stopped for device %s", self.device_id)

    async def get_device_ip(self):
        try:
            if ":" in self.device_id and not self.device_id.startswith("emulator-"):
                ip_part = self.device_id.split(":")[0]
                if DeviceInfoHelper.is_valid_ip(ip_part):
                    self.device_ip = ip_part
                    self.frida_host = ip_part
                    return

            await self.get_device_ip_via_adb()
        except Exception as e:
            logger.error("Error getting device IP: %s", str(e))
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

    async def get_device_ip_via_adb(self):
        try:
            for interface in ["wlan0", "eth0", "eth1", "wlan1"]:
                shell_cmd = (
                    f"ip addr show {interface} | grep 'inet ' | head -1 "
                    f"| awk '{{print $2}}' | cut -d'/' -f1"
                )
                stdout, _, return_code = await execute_adb_shell(
                    device_id=self.device_id, shell_command=shell_cmd
                )
                if return_code == 0:
                    ip = stdout.strip()
                    if ip and ip != "127.0.0.1" and not ip.startswith("169.254"):
                        self.device_ip = ip
                        self.frida_host = ip
                        return

            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()
        except Exception as e:
            logger.error("Error getting device IP via ADB: %s", str(e))
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

    async def setup_port_forwarding(self):
        self.adb_forward_port = await self.find_available_port()
        self.frida_port = self.adb_forward_port
        await self.remove_port_forwarding()
        _, stderr, return_code = await execute_adb_command(
            device_id=self.device_id,
            command=["forward", f"tcp:{self.adb_forward_port}", "tcp:27042"],
        )
        if return_code != 0:
            raise RuntimeError(f"Port forwarding failed: {stderr}")

    async def find_available_port(self, start_port: int = 27043) -> int:
        for port in range(start_port, start_port + 100):
            if await self.is_port_available(port):
                return port
        raise RuntimeError("No available ports found")

    async def is_port_available(self, port: int) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                return sock.connect_ex(("localhost", port)) != 0
        except OSError:
            return False

    async def remove_port_forwarding(self):
        try:
            await remove_all_port_forwarding(device_id=self.device_id)
        except Exception as e:
            logger.warning("Error removing port forwarding: %s", str(e))

    async def detect_device_architecture(self):
        try:
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id, shell_command="getprop ro.product.cpu.abi"
            )
            if return_code == 0:
                arch_map = {
                    "arm64-v8a": "arm64",
                    "armeabi-v7a": "arm",
                    "x86_64": "x86_64",
                    "x86": "x86",
                }
                self.device_arch = arch_map.get(stdout.strip(), stdout.strip())
            else:
                self.device_arch = "arm64"
        except Exception as e:
            logger.error("Error detecting device architecture: %s", str(e))
            self.device_arch = "arm64"

    async def check_frida_installation(self) -> bool:
        try:
            _, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="ls /data/local/tmp/frida-server",
            )
            return return_code == 0
        except Exception as e:
            logger.error("Error checking Frida installation: %s", str(e))
            return False

    async def check_frida_server_status(self) -> bool:
        try:
            stdout, _, _ = await execute_adb_shell(
                device_id=self.device_id, shell_command="ps | grep frida-server"
            )
            return bool(stdout.strip()) and "frida-server" in stdout
        except Exception as e:
            logger.error("Error checking Frida server status: %s", str(e))
            return False

    async def _kill_frida_server(self):
        try:
            await execute_adb_shell(
                device_id=self.device_id, shell_command="su 0 pkill frida-server"
            )
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Error killing Frida server: %s", str(e))

    async def install_frida_server(self):
        try:
            await self.send_response(
                {
                    "type": "frida",
                    "action": "install_progress",
                    "message": "Downloading Frida server...",
                    "progress": 10,
                }
            )

            frida_url = (
                f"https://github.com/frida/frida/releases/download/"
                f"{self.frida_version}/frida-server-"
                f"{self.frida_version}-android-{self.device_arch}.xz"
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                frida_xz_path = os.path.join(temp_dir, "frida-server.xz")
                frida_path = os.path.join(temp_dir, "frida-server")

                dl = await asyncio.create_subprocess_exec(
                    "wget",
                    "-L",
                    "-O",
                    frida_xz_path,
                    frida_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await dl.communicate()
                if dl.returncode != 0:
                    await self.send_error("Failed to download Frida server")
                    return

                ex = await asyncio.create_subprocess_exec(
                    "xz",
                    "-d",
                    frida_xz_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await ex.communicate()
                if ex.returncode != 0:
                    await self.send_error("Failed to extract Frida server")
                    return

                _, _, rc = await execute_adb_command(
                    device_id=self.device_id,
                    command=["push", frida_path, "/data/local/tmp/frida-server"],
                )
                if rc != 0:
                    await self.send_error("Failed to push Frida server to device")
                    return

                _, _, rc = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command="chmod 755 /data/local/tmp/frida-server",
                )
                if rc != 0:
                    await self.send_error("Failed to set executable permissions for Frida server")
                    return

                await self.send_response(
                    {
                        "type": "frida",
                        "action": "install_complete",
                        "message": "Frida server installed successfully",
                        "progress": 100,
                    }
                )
        except Exception as e:
            logger.error("Error installing Frida server: %s", str(e))
            await self.send_error(f"Error installing Frida server: {str(e)}")

    async def start_frida_server(self):
        try:
            if await self.check_frida_server_status():
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "server_status",
                        "running": True,
                        "message": "Frida server is already running",
                    }
                )
                return

            await execute_adb_shell(
                device_id=self.device_id,
                shell_command=(
                    "nohup su 0 /data/local/tmp/frida-server -l 0.0.0.0:27042 "
                    "> /dev/null 2>&1 &"
                ),
            )
            await asyncio.sleep(3)

            running = await self.check_frida_server_status()
            await self.send_response(
                {
                    "type": "frida",
                    "action": "server_status",
                    "running": running,
                    "message": (
                        "Frida server started with root privileges"
                        if running
                        else "Failed to start Frida server"
                    ),
                }
            )
        except Exception as e:
            logger.error("Error starting Frida server: %s", str(e))
            await self.send_error(f"Error starting Frida server: {str(e)}")

    async def stop_frida_server(self):
        try:
            await self._kill_frida_server()
            running = await self.check_frida_server_status()
            await self.send_response(
                {
                    "type": "frida",
                    "action": "server_status",
                    "running": running,
                    "message": (
                        "Frida server stopped successfully"
                        if not running
                        else "Failed to stop Frida server"
                    ),
                }
            )
        except Exception as e:
            logger.error("Error stopping Frida server: %s", str(e))
            await self.send_error(f"Error stopping Frida server: {str(e)}")

    async def load_script(self, script_name: str, script_content: str = None):
        try:
            existing_script = await self.script_service.get_script_by_name(script_name)

            if existing_script:
                if script_content is not None:
                    await self.script_service.update_script(script_name, script_content)
                    message = f"Script '{script_name}' updated successfully"
                else:
                    message = f"Script '{script_name}' already exists"
            else:
                if script_content is None:
                    await self.send_error(
                        f"Script content is required for new script '{script_name}'"
                    )
                    return
                await self.script_service.create_script(script_name, script_content)
                message = f"Script '{script_name}' created and loaded successfully"

            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_loaded",
                    "script_name": script_name,
                    "message": message,
                }
            )
        except Exception as e:
            logger.error("Error loading script: %s", str(e))
            await self.send_error(f"Error loading script: {str(e)}")

    async def list_scripts(self, include_content: bool = False):
        try:
            scripts = await self.script_service.list_scripts()
            if include_content:
                for script in scripts:
                    script["content"] = await self.script_service.get_script_content(
                        script["name"]
                    )
            await self.send_response(
                {"type": "frida", "action": "scripts_list", "scripts": scripts}
            )
        except Exception as e:
            logger.error("Error listing scripts: %s", str(e))
            await self.send_error(f"Error listing scripts: {str(e)}")

    async def get_script_info(self, script_name: str):
        try:
            script_info = await self.script_service.get_script_by_name(script_name)
            if script_info:
                await self.send_response(
                    {"type": "frida", "action": "script_info", "script": script_info}
                )
            else:
                await self.send_error(f"Script '{script_name}' not found")
        except Exception as e:
            logger.error("Error getting script info: %s", str(e))
            await self.send_error(f"Error getting script info: {str(e)}")

    async def delete_script(self, script_name: str):
        try:
            success = await self.script_service.delete_script(script_name)
            if success:
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_deleted",
                        "script_name": script_name,
                        "message": f"Script '{script_name}' deleted successfully",
                    }
                )
            else:
                await self.send_error(f"Failed to delete script '{script_name}'")
        except Exception as e:
            logger.error("Error deleting script: %s", str(e))
            await self.send_error(f"Error deleting script: {str(e)}")

    async def get_script_stats(self):
        try:
            stats = await self.script_service.get_script_stats()
            await self.send_response(
                {"type": "frida", "action": "script_stats", "stats": stats}
            )
        except Exception as e:
            logger.error("Error getting script stats: %s", str(e))
            await self.send_error(f"Error getting script stats: {str(e)}")

    async def _handle_script_message(
        self, script_name: str, message: Dict[str, Any], data: Any
    ):
        try:
            msg_type = message.get("type")
            if msg_type == "error":
                output = message.get("description") or str(message)
                if message.get("stack"):
                    output = f"{output}\n{message['stack']}"
                stream = "stderr"
            else:
                payload = message.get("payload")
                output = payload if payload is not None else message
                stream = msg_type or "send"

            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_output",
                    "script_name": script_name,
                    "output": output,
                    "stream": stream,
                }
            )
        except Exception as e:
            logger.error("Error handling Frida script message: %s", str(e))

    async def _handle_script_log(self, script_name: str, level: str, text: str):
        try:
            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_output",
                    "script_name": script_name,
                    "output": text,
                    "stream": level,
                }
            )
        except Exception as e:
            logger.error("Error handling Frida script log: %s", str(e))

    def _schedule_async(self, loop: asyncio.AbstractEventLoop, coro):
        asyncio.run_coroutine_threadsafe(coro, loop)

    async def run_script(self, script_name: str, target_process: str):
        try:
            script_content = await self.script_service.get_script_content(script_name)
            if script_content is None:
                await self.send_error(f"Script '{script_name}' not found")
                return

            await self._cleanup_frida_session()

            loop = asyncio.get_event_loop()
            bundle = await loop.run_in_executor(
                None, compile_script, script_name, script_content
            )

            self.frida_device = await loop.run_in_executor(
                None, self._get_frida_device_sync
            )

            def _attach_and_create():
                spawn_pid = None
                if target_process.startswith("package:"):
                    package = target_process.replace("package:", "")
                    spawn_pid = self.frida_device.spawn([package])
                    session = self.frida_device.attach(spawn_pid)
                else:
                    try:
                        session = self.frida_device.attach(int(target_process))
                    except ValueError:
                        session = self.frida_device.attach(target_process)

                script = session.create_script(bundle)
                return session, script, spawn_pid

            self.frida_session, self.frida_script, self.spawn_pid = (
                await loop.run_in_executor(None, _attach_and_create)
            )

            def _on_message(message, data):
                logger.debug("Frida script message: %s", message)
                self._schedule_async(
                    loop,
                    self._handle_script_message(script_name, message, data),
                )

            def _on_log(level, text):
                logger.debug("Frida script log [%s]: %s", level, text)
                self._schedule_async(
                    loop,
                    self._handle_script_log(script_name, level, text),
                )

            self.frida_script.on("message", _on_message)
            self.frida_script.set_log_handler(_on_log)

            logger.info("About to load script, bundle length=%d", len(bundle))
            await loop.run_in_executor(None, self.frida_script.load)
            logger.info("Script loaded successfully")

            if self.spawn_pid is not None:
                await loop.run_in_executor(
                    None, lambda: self.frida_device.resume(self.spawn_pid)
                )

            self.current_script_name = script_name

            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_started",
                    "script_name": script_name,
                    "target_process": target_process,
                    "message": f"Script '{script_name}' started against '{target_process}'",
                }
            )
        except Exception as e:
            logger.error("Error running script: %s", str(e))
            await self.send_error(f"Error running script: {str(e)}")

    async def stop_script(self, script_name: str):
        try:
            if not self.frida_script and not self.frida_session:
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_stopped",
                        "script_name": script_name,
                        "message": "No script is currently running",
                    }
                )
                return

            await self._cleanup_frida_session()
            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_stopped",
                    "script_name": script_name,
                    "message": f"Script '{script_name}' stopped",
                }
            )
        except Exception as e:
            logger.error("Error stopping script: %s", str(e))
            await self.send_error(f"Error stopping script: {str(e)}")

    async def list_processes(self):
        try:
            loop = asyncio.get_event_loop()
            device = await loop.run_in_executor(None, self._get_frida_device_sync)

            def _enumerate() -> List[Dict[str, str]]:
                return [
                    {"pid": str(p.pid), "name": p.name or str(p.pid)}
                    for p in device.enumerate_processes()
                ]

            processes = await loop.run_in_executor(None, _enumerate)
            await self.send_response(
                {"type": "frida", "action": "processes_list", "processes": processes}
            )
        except Exception as e:
            logger.error("Error listing processes: %s", str(e))
            await self.send_error(f"Error listing processes: {str(e)}")

    async def _cleanup_frida_session(self):
        loop = asyncio.get_event_loop()
        try:
            if self.frida_script:
                try:
                    await loop.run_in_executor(None, self.frida_script.unload)
                except Exception as e:
                    logger.warning("Error unloading Frida script: %s", str(e))

            if self.frida_session:
                try:
                    await loop.run_in_executor(None, self.frida_session.detach)
                except Exception as e:
                    logger.warning("Error detaching Frida session: %s", str(e))
        finally:
            self.frida_script = None
            self.frida_session = None
            self.frida_device = None
            self.current_script_name = None
            self.spawn_pid = None

    async def handle_message(self, data: str):
        try:
            message = json.loads(data)
            if message.get("type") == "frida":
                await self.handle_frida_command(message)
            else:
                logger.warning("Unknown message type: %s", message.get("type"))
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error("Error handling Frida message: %s", str(e))
            await self.send_error(f"Error processing message: {str(e)}")

    async def handle_frida_command(self, message: Dict[str, Any]):
        action = message.get("action")
        logger.info(f"Get action: {action}")
        dispatch = {
            "install": self.install_frida_server,
            "start_server": self.start_frida_server,
            "stop_server": self.stop_frida_server,
            "list_processes": self.list_processes,
            "get_script_stats": self.get_script_stats,
        }

        if action in dispatch:
            await dispatch[action]()
        elif action == "list_scripts":
            await self.list_scripts(message.get("include_content", False))
        elif action == "load_script":
            await self.load_script(
                message.get("script_name"), message.get("script_content")
            )
        elif action == "run_script":
            await self.run_script(
                message.get("script_name"), message.get("target_process")
            )
        elif action == "stop_script":
            await self.stop_script(message.get("script_name"))
        elif action == "get_script_info":
            await self.get_script_info(message.get("script_name"))
        elif action == "delete_script":
            await self.delete_script(message.get("script_name"))
        elif action == "status":
            frida_installed = await self.check_frida_installation()
            frida_running = await self.check_frida_server_status()
            await self.send_response(
                {
                    "type": "frida",
                    "action": "status",
                    "frida_installed": frida_installed,
                    "frida_running": frida_running,
                    "device_arch": self.device_arch,
                    "frida_version": self.frida_version,
                }
            )
        else:
            logger.warning("Unknown Frida action: %s", action)
            await self.send_error(f"Unknown action: {action}")
