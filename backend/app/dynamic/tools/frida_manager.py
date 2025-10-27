import asyncio
import json
import logging
import os
import re
import socket
import tempfile
from typing import Any, Dict, List

from fastapi import WebSocket

from app.core.app_manager import AsyncStorageService
from app.dynamic.communication.base_websocket_manager import BaseWebSocketManager
from app.dynamic.device_management.emulator_manager import EmulatorManager
from app.dynamic.tools.frida_script_service import FridaScriptService
from app.dynamic.utils.device_info_helper import DeviceInfoHelper
from app.dynamic.utils.adb_utils import remove_all_port_forwarding
from app.dynamic.utils.adb_utils import execute_adb_shell, execute_adb_command


logger = logging.getLogger(__name__)


class FridaManager(BaseWebSocketManager):
    def __init__(self, websocket: WebSocket, device_id: str):
        super().__init__(websocket, "frida")
        self.device_id = device_id
        self.is_running = False
        self.frida_process = None
        self.frida_server_process = None
        self.device_arch = None
        self.frida_version = "16.1.4"
        self.active_sessions = {}
        self.frida_host = None
        self.frida_port = 27042
        self.device_ip = None
        self.emulator_manager = None
        self.adb_forward_port = None
        self.current_script_file = None
        self.process_monitor_task = None
        self.current_script_name = None

        self.script_service = FridaScriptService()

    async def start(self):
        """Starts the Frida manager"""
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

    async def get_device_ip(self):
        """Get device IP address using existing EmulatorManager functionality"""
        try:
            logger.info("Getting IP address for device %s", self.device_id)

            if ":" in self.device_id and not self.device_id.startswith("emulator-"):
                ip_part = self.device_id.split(":")[0]

                if self._is_valid_ip(ip_part):
                    self.device_ip = ip_part
                    self.frida_host = ip_part
                    logger.info("Using IP from device_id: %s", self.device_ip)
                    return

            try:
                redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
                emulators_path = os.getenv("EMULATORS_PATH", "emulators")
                self.emulator_manager = EmulatorManager(redis_url, emulators_path)

                emulators = await self.emulator_manager.list_emulators()

                for emulator in emulators:
                    if emulator.get("status") == "running" and emulator.get(
                        "container_id"
                    ):
                        # pylint: disable=protected-access
                        container_ip = self.emulator_manager._get_container_ip(
                            emulator["container_id"]
                        )
                        if container_ip:
                            if f"{container_ip}:5555" == self.device_id:
                                self.device_ip = container_ip
                                self.frida_host = container_ip
                                logger.info(
                                    "Found matching emulator IP: %s",
                                    self.device_ip,
                                )
                                return

            except Exception as e:
                logger.debug("Could not use EmulatorManager: %s", str(e))

            await self.get_device_ip_via_adb()

        except Exception as e:
            logger.error("Error getting device IP: %s", str(e))
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is a valid IP address"""
        return DeviceInfoHelper.is_valid_ip(ip)

    async def get_device_ip_via_adb(self):
        """Get device IP address via ADB commands (fallback method)"""
        try:
            logger.info("Getting IP via ADB for device %s", self.device_id)

            interfaces = ["wlan0", "eth0", "eth1", "wlan1"]

            for interface in interfaces:
                try:
                    shell_cmd = (
                        f"ip addr show {interface} | grep 'inet ' | head -1 "
                        f"| awk '{{print $2}}' | cut -d'/' -f1"
                    )
                    stdout, _, return_code = await execute_adb_shell(
                        device_id=self.device_id,
                        shell_command=shell_cmd
                    )

                    if return_code == 0:
                        ip = stdout.strip()
                        if ip and ip != "127.0.0.1" and not ip.startswith("169.254"):
                            self.device_ip = ip
                            self.frida_host = ip
                            logger.info(
                                "Found device IP: %s on interface %s",
                                self.device_ip,
                                interface,
                            )
                            return

                except Exception as e:
                    logger.debug("Failed to get IP from %s: %s", interface, str(e))
                    continue

            logger.warning(
                "Could not determine device IP via ADB, "
                "falling back to localhost with port forwarding"
            )
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

        except Exception as e:
            logger.error("Error getting device IP via ADB: %s", str(e))
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

    async def setup_port_forwarding(self):
        """Setup ADB port forwarding for Frida server (fallback when IP not available)"""
        try:
            self.adb_forward_port = await self.find_available_port()
            self.frida_port = self.adb_forward_port

            logger.info(
                "Setting up port forwarding %s:27042 for device %s",
                self.adb_forward_port,
                self.device_id,
            )

            await self.remove_port_forwarding()

            _, stderr, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=f"forward tcp:{self.adb_forward_port} tcp:27042"
            )

            if return_code == 0:
                logger.info(
                    "Port forwarding setup successful: %s:27042",
                    self.adb_forward_port,
                )
            else:
                logger.error("Failed to setup port forwarding: %s", stderr)
                raise RuntimeError(f"Port forwarding failed: {stderr}")

        except Exception as e:
            logger.error("Error setting up port forwarding: %s", str(e))
            raise

    async def find_available_port(self, start_port: int = 27043) -> int:
        """Find an available port starting from start_port"""
        for port in range(start_port, start_port + 100):
            if await self.is_port_available(port):
                return port
        raise Exception("No available ports found")

    async def is_port_available(self, port: int) -> bool:
        """Check if a port is available"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("localhost", port))
                return result != 0
        except (OSError, socket.error):
            return False

    async def remove_port_forwarding(self):
        """Remove existing port forwarding for this device"""
        try:
            _, _, _ = await remove_all_port_forwarding(device_id=self.device_id)
        except Exception as e:
            logger.warning("Error removing port forwarding: %s", str(e))

    async def get_frida_connection_args(self) -> List[str]:
        """Get Frida connection arguments"""
        if self.frida_host and self.frida_port:
            return ["-H", f"{self.frida_host}:{self.frida_port}"]

        return ["-U"]

    async def detect_device_architecture(self):
        """Detect device architecture"""
        try:
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="getprop ro.product.cpu.abi"
            )

            if return_code == 0:
                arch = stdout.strip()
                arch_map = {
                    "arm64-v8a": "arm64",
                    "armeabi-v7a": "arm",
                    "x86_64": "x86_64",
                    "x86": "x86",
                }
                self.device_arch = arch_map.get(arch, arch)
                logger.info("Device architecture: %s", self.device_arch)
            else:
                logger.warning("Failed to detect architecture")
                self.device_arch = "arm64"

        except Exception as e:
            logger.error("Error detecting device architecture: %s", str(e))
            self.device_arch = "arm64"

    async def check_frida_installation(self) -> bool:
        """Check if Frida server is installed on device"""
        try:
            _, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="ls /data/local/tmp/frida-server"
            )

            installed = return_code == 0
            logger.info("Frida server installed: %s", installed)
            return installed

        except Exception as e:
            logger.error("Error checking Frida installation: %s", str(e))
            return False

    async def check_frida_server_status(self) -> bool:
        """Check if Frida server is running"""
        try:
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="ps | grep frida-server"
            )

            output = stdout.strip()
            if output and "frida-server" in output:
                logger.info("Frida server running (ps method): True")
                return True

            logger.info("Frida server running: False")
            return False

        except Exception as e:
            logger.error("Error checking Frida server status: %s", str(e))
            return False

    async def _kill_frida_server(self):
        """Kill Frida server processes using su privileges"""
        try:
            _, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="su 0 pkill frida-server"
            )

            await asyncio.sleep(1)

        except Exception as e:
            logger.warning("Error killing Frida server: %s", str(e))

    async def install_frida_server(self):
        """Install Frida server on device"""
        try:
            logger.info("Installing Frida server for %s", self.device_arch)

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

                download_process = await asyncio.create_subprocess_exec(
                    "wget",
                    "-L",
                    "-O",
                    frida_xz_path,
                    frida_url,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await download_process.communicate()

                if download_process.returncode != 0:
                    await self.send_error("Failed to download Frida server")
                    return

                await self.send_response(
                    {
                        "type": "frida",
                        "action": "install_progress",
                        "message": "Extracting Frida server...",
                        "progress": 50,
                    }
                )

                extract_process = await asyncio.create_subprocess_exec(
                    "xz",
                    "-d",
                    frida_xz_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await extract_process.communicate()

                if extract_process.returncode != 0:
                    await self.send_error("Failed to extract Frida server")
                    return

                await self.send_response(
                    {
                        "type": "frida",
                        "action": "install_progress",
                        "message": "Pushing to device...",
                        "progress": 70,
                    }
                )

                _, _, return_code = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command=f"push {frida_path} /data/local/tmp/frida-server"
                )

                if return_code != 0:
                    await self.send_error("Failed to push Frida server to device")
                    return

                _, _, return_code = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command="chmod 755 /data/local/tmp/frida-server"
                )

                if return_code != 0:
                    await self.send_error(
                        "Failed to set executable permissions for Frida server"
                    )
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
        """Start Frida server on device"""
        try:
            logger.info("Starting Frida server")

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

            await self._kill_frida_server()

            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="nohup su 0 /data/local/tmp/frida-server -l 0.0.0.0:27042 > /dev/null 2>&1 &"
            )

            if return_code != 0:
                await self.send_error("Failed to start Frida server")
                return

            self.frida_server_process = stdout

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
        """Stop Frida server"""
        try:
            logger.info("Stopping Frida server")

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
        """Load a Frida script - saves script to system"""
        try:
            logger.info("Loading script: %s", script_name)

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

    async def _read_frida_output(self, script_name: str):
        """Read output from Frida process"""
        try:
            stdout_task = asyncio.create_task(
                self._read_stream(self.frida_process.stdout, script_name, "stdout")
            )
            stderr_task = asyncio.create_task(
                self._read_stream(self.frida_process.stderr, script_name, "stderr")
            )

            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            if self.current_script_file and os.path.exists(self.current_script_file):
                try:
                    os.unlink(self.current_script_file)
                    self.current_script_file = None
                except Exception as e:
                    logger.warning("Failed to clean up script file: %s", str(e))

        except Exception as e:
            logger.error("Error in Frida output reader: %s", str(e))

    async def _read_stream(self, stream, script_name: str, stream_type: str):
        """Read output from a specific stream (stdout or stderr)"""
        try:
            while self.frida_process and self.frida_process.returncode is None:
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                    if line:
                        output = line.decode("utf-8", errors="replace").strip()
                        if output:
                            processed_output = self._process_frida_output(output)
                            if processed_output:
                                logger.info(
                                    "Frida %s output: %s", stream_type, processed_output
                                )
                                await self.send_response(
                                    {
                                        "type": "frida",
                                        "action": "script_output",
                                        "script_name": script_name,
                                        "output": processed_output,
                                        "stream": stream_type,
                                    }
                                )
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error("Error reading Frida %s: %s", stream_type, str(e))
                    break

        except Exception as e:
            logger.error("Error in Frida %s reader: %s", stream_type, str(e))

    def _process_frida_output(self, output: str) -> str:
        """Process and clean up Frida output"""
        try:
            if not output.strip():
                return ""

            skip_patterns = [
                "____",
                "/ _  |",
                "| (_| |",
                "> _  |",
                "/_/ |_|",
                ". . . .",
                "Commands:",
                "help      ->",
                "object?   ->",
                "exit/quit ->",
                "More info at",
                "Connected to",
                "Attaching...",
                "Spawning...",
                "Resumed",
                "Process resumed",
                "Process terminated",
            ]

            for pattern in skip_patterns:
                if pattern in output:
                    return ""

            if "{'type': 'send', 'payload':" in output:
                try:

                    match = re.search(r"'payload': '([^']*)'", output)
                    if match:
                        payload = match.group(1)
                        return payload
                except Exception as e:
                    logger.debug("Error parsing Frida message: %s", e)
                    return output

            if '"payload":' in output:
                try:
                    match = re.search(r'"payload":\s*"([^"]*)"', output)
                    if match:
                        payload = match.group(1)
                        return payload
                except Exception as e:
                    logger.debug("Error parsing JSON message: %s", e)
                    return output

            if "console.log" in output.lower() or "[INFO]" in output:
                return output

            if "error" in output.lower() or "exception" in output.lower():
                return output

            return output.strip()

        except Exception as e:
            logger.debug("Error processing Frida output: %s", e)
            return output

    async def run_script(self, script_name: str, target_process: str):
        """Run a Frida script against a target process"""
        try:
            logger.info("Running script '%s' against '%s'", script_name, target_process)

            script_content = await self.script_service.get_script_content(script_name)
            if script_content is None:
                await self.send_error(f"Script '{script_name}' not found")
                return

            if self.current_script_file and os.path.exists(self.current_script_file):
                try:
                    os.unlink(self.current_script_file)
                except:
                    pass

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", delete=False
            ) as temp_script:
                temp_script.write(script_content)
                temp_script_path = temp_script.name

            self.current_script_file = temp_script_path

            connection_args = await self.get_frida_connection_args()

            if target_process.startswith("package:"):
                cmd = (
                    ["frida"]
                    + connection_args
                    + [
                        "-q",
                        "-f",
                        target_process.replace("package:", ""),
                        "-l",
                        temp_script_path,
                        "--runtime=qjs",
                    ]
                )
            else:
                cmd = (
                    ["frida"]
                    + connection_args
                    + [
                        "-q",
                        "-n",
                        target_process,
                        "-l",
                        temp_script_path,
                        "--runtime=qjs",
                    ]
                )

            logger.info("Running Frida command: %s", " ".join(cmd))

            self.frida_process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            asyncio.create_task(self._read_frida_output(script_name))

            self.current_script_name = script_name

            self.process_monitor_task = asyncio.create_task(
                self._monitor_process_completion(script_name)
            )

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
        """Stop running Frida script"""
        try:
            if self.frida_process:
                logger.info("Stopping script '%s'", script_name)

                if self.frida_process.returncode is not None:
                    logger.info(
                        "Process already terminated with code: %s",
                        self.frida_process.returncode,
                    )
                    await self._handle_already_terminated_process(script_name)
                    return

                if self.process_monitor_task and not self.process_monitor_task.done():
                    self.process_monitor_task.cancel()
                    logger.info("Cancelled process monitor task")

                await self._terminate_frida_process()
                await self._wait_for_process_termination()
                self._cleanup_script_resources()

                await self._notify_script_stopped(script_name, f"Script '{script_name}' stopped")
            else:
                logger.info("No script process to stop")
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_stopped",
                        "script_name": script_name,
                        "message": "No script is currently running",
                    }
                )

        except Exception as e:
            error_msg = f"Error stopping script: {str(e)} ({type(e).__name__})"
            if not str(e):
                error_msg = (
                    f"Error stopping script: {type(e).__name__} (no error message)"
                )
            logger.error(error_msg)
            await self.send_error(error_msg)

    async def list_processes(self):
        """List running processes on device"""
        try:
            logger.info("Listing processes")

            connection_args = await self.get_frida_connection_args()

            frida_ps_paths = [
                "frida-ps",
                "/usr/local/bin/frida-ps",
                "/usr/bin/frida-ps",
            ]

            cmd = None
            for path in frida_ps_paths:
                try:
                    test_cmd = [path] + connection_args
                    test_process = await asyncio.create_subprocess_exec(
                        *test_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await test_process.communicate()

                    if test_process.returncode == 0:
                        cmd = test_cmd
                        break

                    logger.debug("Failed to run %s: %s", path, stderr.decode())
                except Exception as e:
                    logger.debug("Error testing %s: %s", path, str(e))
                    continue

            if not cmd:
                await self.send_error("frida-ps not found or not working")
                return

            logger.info("Running frida-ps command: %s", " ".join(cmd))

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                processes = []

                lines = output.split("\n")
                if len(lines) > 1:
                    for line in lines[1:]:
                        if line.strip():
                            if line.strip().startswith("-") or "----" in line:
                                continue

                            parts = line.strip().split(None, 1)
                            if len(parts) >= 2:
                                pid = parts[0]
                                name = parts[1]

                                if pid.isdigit() and not "-" in pid:
                                    processes.append({"pid": pid, "name": name})

                await self.send_response(
                    {
                        "type": "frida",
                        "action": "processes_list",
                        "processes": processes,
                    }
                )
            else:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                await self.send_error(f"Failed to list processes: {error_msg}")

        except Exception as e:
            logger.error("Error listing processes: %s", str(e))
            await self.send_error(f"Error listing processes: {str(e)}")

    async def list_scripts(self):
        """List all available scripts"""
        try:
            logger.info("Listing scripts")
            scripts = await self.script_service.list_scripts()

            await self.send_response(
                {
                    "type": "frida",
                    "action": "scripts_list",
                    "scripts": scripts,
                }
            )
        except Exception as e:
            logger.error("Error listing scripts: %s", str(e))
            await self.send_error(f"Error listing scripts: {str(e)}")

    async def get_script_info(self, script_name: str):
        """Get information about a specific script"""
        try:
            logger.info("Getting script info: %s", script_name)
            script_info = await self.script_service.get_script_by_name(script_name)

            if script_info:
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_info",
                        "script": script_info,
                    }
                )
            else:
                await self.send_error(f"Script '{script_name}' not found")
        except Exception as e:
            logger.error("Error getting script info: %s", str(e))
            await self.send_error(f"Error getting script info: {str(e)}")

    async def delete_script(self, script_name: str):
        """Delete a script"""
        try:
            logger.info("Deleting script: %s", script_name)
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
        """Get statistics about scripts"""
        try:
            logger.info("Getting script stats")
            stats = await self.script_service.get_script_stats()

            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_stats",
                    "stats": stats,
                }
            )
        except Exception as e:
            logger.error("Error getting script stats: %s", str(e))
            await self.send_error(f"Error getting script stats: {str(e)}")

    async def install_app(self, file_hash: str, app_name: str):
        """Install an APK file on the device"""
        try:
            logger.info("Installing app: %s (%s)", app_name, file_hash)

            await self.send_response(
                {
                    "type": "frida",
                    "action": "app_install_start",
                    "app_name": app_name,
                    "file_hash": file_hash,
                }
            )

            storage = AsyncStorageService()

            file_info = await storage.get_scan_status(file_hash)
            if not file_info:
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "app_install_error",
                        "message": "File not found in storage",
                    }
                )
                return

            if file_info.get("file_type") != "apk":
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "app_install_error",
                        "message": "File is not an APK",
                    }
                )
                return

            storage_dir = "/shared_data"
            folder_path = file_info.get("folder_path")
            original_name = file_info.get("original_name")

            apk_path = os.path.join(storage_dir, folder_path, original_name)

            if not os.path.exists(apk_path):
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "app_install_error",
                        "message": f"APK file not found at: {apk_path}",
                    }
                )
                return

            await self.send_response(
                {
                    "type": "frida",
                    "action": "app_install_progress",
                    "message": f"Installing {app_name} to device...",
                }
            )

            stdout, stderr, return_code = await execute_adb_command(
                device_id=self.device_id,
                command=["install", "-r", apk_path]
            )

            if return_code == 0:
                success_msg = f"Successfully installed {app_name}"
                logger.info(success_msg)
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "app_install_success",
                        "app_name": app_name,
                        "message": success_msg,
                    }
                )
            else:
                error_output = (
                    stderr.strip() if stderr else stdout.strip()
                )
                error_msg = f"Failed to install {app_name}: {error_output}"
                logger.error(error_msg)
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "app_install_error",
                        "message": error_msg,
                    }
                )

        except Exception as e:
            error_msg = f"Error installing app: {str(e)}"
            logger.error(error_msg)
            await self.send_response(
                {"type": "frida", "action": "app_install_error", "message": error_msg}
            )

    async def handle_message(self, data: str):
        """Handle incoming messages from WebSocket"""
        try:
            logger.info("Received Frida message: %s", data)

            message = json.loads(data)
            if message.get("type") == "frida":
                await self.handle_frida_command(message)
            else:
                logger.warning("Unknown message type: %s", message.get("type"))

        except json.JSONDecodeError:
            logger.error("Invalid JSON in Frida message")
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error("Error handling Frida message: %s", str(e))
            await self.send_error(f"Error processing message: {str(e)}")

    async def handle_frida_command(self, message: Dict[str, Any]):
        """Handle Frida commands"""
        action = message.get("action")

        if action == "install":
            await self.install_frida_server()
        elif action == "start_server":
            await self.start_frida_server()
        elif action == "stop_server":
            await self.stop_frida_server()
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
        elif action == "list_processes":
            await self.list_processes()
        elif action == "list_scripts":
            await self.list_scripts()
        elif action == "get_script_info":
            await self.get_script_info(message.get("script_name"))
        elif action == "delete_script":
            await self.delete_script(message.get("script_name"))
        elif action == "get_script_stats":
            await self.get_script_stats()
        elif action == "install_app":
            await self.install_app(message.get("file_hash"), message.get("app_name"))
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
                }
            )
        else:
            logger.warning("Unknown Frida action: %s", action)
            await self.send_error(f"Unknown action: {action}")

    async def stop(self):
        """Stop Frida manager"""
        if not self.is_running:
            return

        self.is_running = False

        if self.process_monitor_task and not self.process_monitor_task.done():
            self.process_monitor_task.cancel()
            logger.info("Cancelled process monitor task")

        if self.frida_process:
            try:
                self.frida_process.terminate()
                await self.frida_process.wait()
            except (ProcessLookupError, AttributeError):
                pass

        self.frida_process = None
        self.current_script_name = None
        self.process_monitor_task = None

        if self.current_script_file and os.path.exists(self.current_script_file):
            try:
                os.unlink(self.current_script_file)
                self.current_script_file = None
            except (OSError, FileNotFoundError):
                pass

        if self.frida_host == "localhost" and hasattr(self, "adb_forward_port"):
            await self.remove_port_forwarding()

        logger.info("Frida manager stopped for device %s", self.device_id)

    async def _monitor_process_completion(self, script_name: str):
        """Monitor Frida process completion"""
        try:
            if not self.frida_process:
                return

            logger.info("Starting process monitor for script '%s'", script_name)

            returncode = await self.frida_process.wait()

            logger.info("Process completed with return code: %s", returncode)

            if self.current_script_file and os.path.exists(self.current_script_file):
                try:
                    os.unlink(self.current_script_file)
                    self.current_script_file = None
                    logger.info("Cleaned up script file")
                except Exception as e:
                    logger.warning("Failed to clean up script file: %s", str(e))

            self.frida_process = None
            self.current_script_name = None
            self.process_monitor_task = None

            if returncode == 0:
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_completed",
                        "script_name": script_name,
                        "message": f"Script '{script_name}' completed successfully",
                        "return_code": returncode,
                    }
                )
            else:
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_completed",
                        "script_name": script_name,
                        "message": (
                            f"Script '{script_name}' completed "
                            f"with errors (code: {returncode})"
                        ),
                        "return_code": returncode,
                    }
                )

        except Exception as e:
            error_msg = (
                f"Error monitoring process completion: {str(e)} ({type(e).__name__})"
            )
            logger.error(error_msg)

            self.frida_process = None
            self.current_script_name = None
            self.process_monitor_task = None

            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_completed",
                    "script_name": script_name,
                    "message": f"Script '{script_name}' completed with monitoring error: {str(e)}",
                    "return_code": -1,
                }
            )

    async def _notify_script_stopped(self, script_name: str, message: str):
        """Send notification that script was stopped"""
        await self.send_response(
            {
                "type": "frida",
                "action": "script_stopped",
                "script_name": script_name,
                "message": message,
            }
        )

    async def _terminate_frida_process(self):
        """Terminate Frida process gracefully"""
        try:
            self.frida_process.terminate()
            logger.info("Sent SIGTERM to process")
        except ProcessLookupError:
            logger.info("Process already terminated")
            self.frida_process = None
        except Exception as e:
            logger.warning(
                "Error terminating process: %s (%s)",
                str(e),
                type(e).__name__,
            )

    async def _wait_for_process_termination(self):
        """Wait for process to terminate, with timeout and kill fallback"""
        if not self.frida_process:
            return

        try:
            await asyncio.wait_for(self.frida_process.wait(), timeout=5.0)
            logger.info("Process terminated gracefully")
        except asyncio.TimeoutError:
            logger.warning("Process did not terminate gracefully, forcing kill")
            try:
                self.frida_process.kill()
                await self.frida_process.wait()
                logger.info("Process force killed")
            except ProcessLookupError:
                logger.info("Process already terminated during force kill")
            except Exception as e:
                logger.error(
                    "Error force killing process: %s (%s)",
                    str(e),
                    type(e).__name__,
                )
        except Exception as e:
            logger.error(
                "Error waiting for process termination: %s (%s)",
                str(e),
                type(e).__name__,
            )

    def _cleanup_script_resources(self):
        """Clean up script file and reset process state"""
        self.frida_process = None
        self.current_script_name = None
        self.process_monitor_task = None

        if self.current_script_file and os.path.exists(self.current_script_file):
            try:
                os.unlink(self.current_script_file)
                self.current_script_file = None
                logger.info("Cleaned up script file")
            except Exception as e:
                logger.warning(
                    "Failed to clean up script file: %s (%s)",
                    str(e),
                    type(e).__name__,
                )

    async def _handle_already_terminated_process(self, script_name: str):
        """Handle case when process is already terminated"""
        if (
            self.process_monitor_task
            and not self.process_monitor_task.done()
        ):
            self.process_monitor_task.cancel()
            logger.info("Cancelled process monitor task")

        self._cleanup_script_resources()

        await self.send_response(
            {
                "type": "frida",
                "action": "script_stopped",
                "script_name": script_name,
                "message": f"Script '{script_name}' was already completed",
            }
        )
