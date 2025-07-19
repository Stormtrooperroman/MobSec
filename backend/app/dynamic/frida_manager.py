import asyncio
import json
import logging
import os
import tempfile
from typing import Optional, Dict, Any, List
from fastapi import WebSocket
import subprocess
import base64
import socket

logger = logging.getLogger(__name__)


class FridaManager:
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.is_running = False
        self.frida_process = None
        self.frida_server_process = None
        self.device_arch = None
        self.frida_version = "16.1.4"
        self.scripts = {}
        self.active_sessions = {}
        self.frida_host = None
        self.frida_port = 27042
        self.device_ip = None
        self.emulator_manager = None
        self.adb_forward_port = None
        self.current_script_file = None
        self.process_monitor_task = None
        self.current_script_name = None

    async def start(self):
        """Starts the Frida manager"""
        if self.is_running:
            return True

        try:
            self.is_running = True
            logger.info(f"Starting Frida manager for device {self.device_id}")

            # Get device IP address
            await self.get_device_ip()

            # Check device architecture
            await self.detect_device_architecture()

            # Check if Frida server is installed
            frida_installed = await self.check_frida_installation()

            # Check if Frida server is running
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
            logger.error(f"Error starting Frida manager: {str(e)}")
            self.is_running = False
            return False

    async def get_device_ip(self):
        """Get device IP address using existing EmulatorManager functionality"""
        try:
            logger.info(f"Getting IP address for device {self.device_id}")

            # Import here to avoid circular imports
            from app.dynamic.emulator_manager import EmulatorManager

            # Try to get IP from device_id if it's already an IP:port format
            if ":" in self.device_id and not self.device_id.startswith("emulator-"):
                # Extract IP from device_id (format: "192.168.1.100:5555")
                ip_part = self.device_id.split(":")[0]

                # Validate it's a valid IP
                if self._is_valid_ip(ip_part):
                    self.device_ip = ip_part
                    self.frida_host = ip_part
                    logger.info(f"Using IP from device_id: {self.device_ip}")
                    return

            # Try to get emulator manager instance
            try:
                # Create EmulatorManager instance
                redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
                emulators_path = os.getenv("EMULATORS_PATH", "emulators")
                self.emulator_manager = EmulatorManager(redis_url, emulators_path)

                # Get list of emulators
                emulators = await self.emulator_manager.list_emulators()

                # Try to find matching emulator by checking if device_id contains container IP
                for emulator in emulators:
                    if emulator.get("status") == "running" and emulator.get(
                        "container_id"
                    ):
                        container_ip = self.emulator_manager._get_container_ip(
                            emulator["container_id"]
                        )
                        if container_ip:
                            # Check if this container IP matches our device
                            if f"{container_ip}:5555" == self.device_id:
                                self.device_ip = container_ip
                                self.frida_host = container_ip
                                logger.info(
                                    f"Found matching emulator IP: {self.device_ip}"
                                )
                                return

            except Exception as e:
                logger.debug(f"Could not use EmulatorManager: {str(e)}")

            # Fallback to ADB-based IP detection
            await self.get_device_ip_via_adb()

        except Exception as e:
            logger.error(f"Error getting device IP: {str(e)}")
            # Final fallback to localhost with port forwarding
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

    def _is_valid_ip(self, ip: str) -> bool:
        """Check if string is a valid IP address"""
        try:
            parts = ip.split(".")
            if len(parts) != 4:
                return False
            for part in parts:
                if not 0 <= int(part) <= 255:
                    return False
            return True
        except:
            return False

    async def get_device_ip_via_adb(self):
        """Get device IP address via ADB commands (fallback method)"""
        try:
            logger.info(f"Getting IP via ADB for device {self.device_id}")

            # Try different network interfaces
            interfaces = ["wlan0", "eth0", "eth1", "wlan1"]

            for interface in interfaces:
                try:
                    # Try to get IP using ip command
                    process = await asyncio.create_subprocess_exec(
                        "adb",
                        "-s",
                        self.device_id,
                        "shell",
                        f"ip addr show {interface} | grep 'inet ' | head -1 | awk '{{print $2}}' | cut -d'/' -f1",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        ip = stdout.decode().strip()
                        if ip and ip != "127.0.0.1" and not ip.startswith("169.254"):
                            self.device_ip = ip
                            self.frida_host = ip
                            logger.info(
                                f"Found device IP: {self.device_ip} on interface {interface}"
                            )
                            return

                except Exception as e:
                    logger.debug(f"Failed to get IP from {interface}: {str(e)}")
                    continue

            # If all ADB methods fail, fall back to localhost with port forwarding
            logger.warning(
                f"Could not determine device IP via ADB, falling back to localhost with port forwarding"
            )
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

        except Exception as e:
            logger.error(f"Error getting device IP via ADB: {str(e)}")
            # Final fallback to localhost with port forwarding
            self.device_ip = "localhost"
            self.frida_host = "localhost"
            await self.setup_port_forwarding()

    async def setup_port_forwarding(self):
        """Setup ADB port forwarding for Frida server (fallback when IP not available)"""
        try:
            # Find available local port
            self.adb_forward_port = await self.find_available_port()
            self.frida_port = self.adb_forward_port

            logger.info(
                f"Setting up port forwarding {self.adb_forward_port}:27042 for device {self.device_id}"
            )

            # Remove existing forwarding for this device (if any)
            await self.remove_port_forwarding()

            # Setup new port forwarding
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "forward",
                f"tcp:{self.adb_forward_port}",
                "tcp:27042",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(
                    f"Port forwarding setup successful: {self.adb_forward_port}:27042"
                )
            else:
                logger.error(f"Failed to setup port forwarding: {stderr.decode()}")
                raise Exception(f"Port forwarding failed: {stderr.decode()}")

        except Exception as e:
            logger.error(f"Error setting up port forwarding: {str(e)}")
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
        except:
            return False

    async def remove_port_forwarding(self):
        """Remove existing port forwarding for this device"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "forward",
                "--remove-all",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
        except Exception as e:
            logger.warning(f"Error removing port forwarding: {str(e)}")

    async def get_frida_connection_args(self) -> List[str]:
        """Get Frida connection arguments"""
        if self.frida_host and self.frida_port:
            return ["-H", f"{self.frida_host}:{self.frida_port}"]
        else:
            # Fallback to USB mode
            return ["-U"]

    async def detect_device_architecture(self):
        """Detect device architecture"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "getprop ro.product.cpu.abi",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                arch = stdout.decode().strip()
                # Map Android ABI to Frida architecture
                arch_map = {
                    "arm64-v8a": "arm64",
                    "armeabi-v7a": "arm",
                    "x86_64": "x86_64",
                    "x86": "x86",
                }
                self.device_arch = arch_map.get(arch, arch)
                logger.info(f"Device architecture: {self.device_arch}")
            else:
                logger.warning(f"Failed to detect architecture: {stderr.decode()}")
                self.device_arch = "arm64"  # Default fallback

        except Exception as e:
            logger.error(f"Error detecting device architecture: {str(e)}")
            self.device_arch = "arm64"  # Default fallback

    async def check_frida_installation(self) -> bool:
        """Check if Frida server is installed on device"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "ls /data/local/tmp/frida-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            installed = process.returncode == 0
            logger.info(f"Frida server installed: {installed}")
            return installed

        except Exception as e:
            logger.error(f"Error checking Frida installation: {str(e)}")
            return False

    async def check_frida_server_status(self) -> bool:
        """Check if Frida server is running"""
        try:
            # Try multiple methods to check if frida-server is running

            # Method 1: Check process list with ps
            process1 = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "ps | grep frida-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout1, stderr1 = await process1.communicate()

            output1 = stdout1.decode().strip()
            if output1 and "frida-server" in output1:
                logger.info(f"Frida server running (ps method): True")
                return True

            # Method 2: Check with pgrep (more reliable)
            process2 = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "pgrep frida-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, stderr2 = await process2.communicate()

            output2 = stdout2.decode().strip()
            if output2 and output2.isdigit():
                logger.info(f"Frida server running (pgrep method): True")
                return True

            # Method 3: Check with pidof
            process3 = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "pidof frida-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout3, stderr3 = await process3.communicate()

            output3 = stdout3.decode().strip()
            if output3 and output3.isdigit():
                logger.info(f"Frida server running (pidof method): True")
                return True

            logger.info(f"Frida server running: False")
            return False

        except Exception as e:
            logger.error(f"Error checking Frida server status: {str(e)}")
            return False

    async def _kill_frida_server(self):
        """Kill Frida server processes using su privileges"""
        try:
            kill_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "su 0 pkill frida-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await kill_process.communicate()

            # Wait a bit for processes to stop
            await asyncio.sleep(1)

        except Exception as e:
            logger.warning(f"Error killing Frida server: {str(e)}")

    async def install_frida_server(self):
        """Install Frida server on device"""
        try:
            logger.info(f"Installing Frida server for {self.device_arch}")

            # Download Frida server
            await self.send_response(
                {
                    "type": "frida",
                    "action": "install_progress",
                    "message": "Downloading Frida server...",
                    "progress": 10,
                }
            )

            frida_url = f"https://github.com/frida/frida/releases/download/{self.frida_version}/frida-server-{self.frida_version}-android-{self.device_arch}.xz"

            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                frida_xz_path = os.path.join(temp_dir, "frida-server.xz")
                frida_path = os.path.join(temp_dir, "frida-server")

                # Download file
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

                # Extract xz file
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

                # Push to device
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "install_progress",
                        "message": "Pushing to device...",
                        "progress": 70,
                    }
                )

                push_process = await asyncio.create_subprocess_exec(
                    "adb",
                    "-s",
                    self.device_id,
                    "push",
                    frida_path,
                    "/data/local/tmp/frida-server",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await push_process.communicate()

                if push_process.returncode != 0:
                    await self.send_error("Failed to push Frida server to device")
                    return

                # Make executable
                chmod_process = await asyncio.create_subprocess_exec(
                    "adb",
                    "-s",
                    self.device_id,
                    "shell",
                    "chmod 755 /data/local/tmp/frida-server",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await chmod_process.communicate()

                if chmod_process.returncode != 0:
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
            logger.error(f"Error installing Frida server: {str(e)}")
            await self.send_error(f"Error installing Frida server: {str(e)}")

    async def start_frida_server(self):
        """Start Frida server on device"""
        try:
            logger.info("Starting Frida server")

            # Check if already running
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

            # Kill any existing frida-server processes
            await self._kill_frida_server()

            # Start server with root privileges
            self.frida_server_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "shell",
                "nohup su 0 /data/local/tmp/frida-server -l 0.0.0.0:27042 > /dev/null 2>&1 &",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await self.frida_server_process.communicate()

            # Wait a bit for server to start
            await asyncio.sleep(3)

            # Check if started successfully
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
            logger.error(f"Error starting Frida server: {str(e)}")
            await self.send_error(f"Error starting Frida server: {str(e)}")

    async def stop_frida_server(self):
        """Stop Frida server"""
        try:
            logger.info("Stopping Frida server")

            # Kill Frida server processes
            await self._kill_frida_server()

            # Check if stopped
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
            logger.error(f"Error stopping Frida server: {str(e)}")
            await self.send_error(f"Error stopping Frida server: {str(e)}")

    async def load_script(self, script_name: str, script_content: str):
        """Load a Frida script"""
        try:
            logger.info(f"Loading script: {script_name}")

            # Store script
            self.scripts[script_name] = script_content

            await self.send_response(
                {
                    "type": "frida",
                    "action": "script_loaded",
                    "script_name": script_name,
                    "message": f"Script '{script_name}' loaded successfully",
                }
            )

        except Exception as e:
            logger.error(f"Error loading script: {str(e)}")
            await self.send_error(f"Error loading script: {str(e)}")

    async def _read_frida_output(self, script_name: str):
        """Read output from Frida process"""
        try:
            # Create tasks for reading both stdout and stderr
            stdout_task = asyncio.create_task(
                self._read_stream(self.frida_process.stdout, script_name, "stdout")
            )
            stderr_task = asyncio.create_task(
                self._read_stream(self.frida_process.stderr, script_name, "stderr")
            )

            # Wait for both tasks to complete
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

            # Process has finished, clean up script file
            if self.current_script_file and os.path.exists(self.current_script_file):
                try:
                    os.unlink(self.current_script_file)
                    self.current_script_file = None
                except Exception as e:
                    logger.warning(f"Failed to clean up script file: {str(e)}")

        except Exception as e:
            logger.error(f"Error in Frida output reader: {str(e)}")

    async def _read_stream(self, stream, script_name: str, stream_type: str):
        """Read output from a specific stream (stdout or stderr)"""
        try:
            while self.frida_process and self.frida_process.returncode is None:
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                    if line:
                        output = line.decode("utf-8", errors="replace").strip()
                        if output:
                            # Parse Frida messages and extract useful information
                            processed_output = self._process_frida_output(output)
                            if processed_output:
                                logger.info(
                                    f"Frida {stream_type} output: {processed_output}"
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
                    logger.error(f"Error reading Frida {stream_type}: {str(e)}")
                    break

        except Exception as e:
            logger.error(f"Error in Frida {stream_type} reader: {str(e)}")

    def _process_frida_output(self, output: str) -> str:
        """Process and clean up Frida output"""
        try:
            # Skip empty lines
            if not output.strip():
                return ""

            # Skip Frida banner and help messages
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

            # Extract payload from Frida messages
            if "{'type': 'send', 'payload':" in output:
                try:
                    import re

                    match = re.search(r"'payload': '([^']*)'", output)
                    if match:
                        payload = match.group(1)
                        return f"📱 Script output: {payload}"
                except Exception as e:
                    logger.debug(f"Error parsing Frida message: {e}")
                    return output

            # Extract payload from JSON-like messages
            if '"payload":' in output:
                try:
                    import re

                    match = re.search(r'"payload":\s*"([^"]*)"', output)
                    if match:
                        payload = match.group(1)
                        return f"📱 Script output: {payload}"
                except Exception as e:
                    logger.debug(f"Error parsing JSON message: {e}")
                    return output

            # Handle console.log output
            if "console.log" in output.lower() or "[INFO]" in output:
                return output

            # Handle error messages
            if "error" in output.lower() or "exception" in output.lower():
                return f"❌ Error: {output}"

            # Return cleaned output
            return output.strip()

        except Exception as e:
            logger.debug(f"Error processing Frida output: {e}")
            return output

    async def run_script(self, script_name: str, target_process: str):
        """Run a Frida script against a target process"""
        try:
            logger.info(f"Running script '{script_name}' against '{target_process}'")

            if script_name not in self.scripts:
                await self.send_error(f"Script '{script_name}' not found")
                return

            script_content = self.scripts[script_name]

            # Clean up previous script file if exists
            if self.current_script_file and os.path.exists(self.current_script_file):
                try:
                    os.unlink(self.current_script_file)
                except:
                    pass

            # Create temporary script file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", delete=False
            ) as temp_script:
                temp_script.write(script_content)
                temp_script_path = temp_script.name

            # Store the script file path for cleanup later
            self.current_script_file = temp_script_path

            # Get connection arguments
            connection_args = await self.get_frida_connection_args()

            # Build command - different args for spawn vs attach
            if target_process.startswith("package:"):
                # Spawn mode
                cmd = (
                    ["frida"]
                    + connection_args
                    + [
                        "-q",  # Quiet mode (no banner)
                        "-f",
                        target_process.replace("package:", ""),
                        "-l",
                        temp_script_path,
                        "--runtime=qjs",  # Use QuickJS runtime for better performance
                    ]
                )
            else:
                # Attach mode
                cmd = (
                    ["frida"]
                    + connection_args
                    + [
                        "-q",  # Quiet mode (no banner)
                        "-n",
                        target_process,
                        "-l",
                        temp_script_path,
                        "--runtime=qjs",  # Use QuickJS runtime for better performance
                    ]
                )

            logger.info(f"Running Frida command: {' '.join(cmd)}")

            # Run Frida script
            self.frida_process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )

            # Start reading output
            asyncio.create_task(self._read_frida_output(script_name))

            # Store current script name
            self.current_script_name = script_name

            # Start monitoring process completion
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
            logger.error(f"Error running script: {str(e)}")
            await self.send_error(f"Error running script: {str(e)}")

    async def stop_script(self, script_name: str):
        """Stop running Frida script"""
        try:
            if self.frida_process:
                logger.info(f"Stopping script '{script_name}'")

                # Check if process is still running
                if self.frida_process.returncode is not None:
                    logger.info(
                        f"Process already terminated with code: {self.frida_process.returncode}"
                    )

                    # Cancel monitoring task if it exists
                    if (
                        self.process_monitor_task
                        and not self.process_monitor_task.done()
                    ):
                        self.process_monitor_task.cancel()
                        logger.info("Cancelled process monitor task")

                    # Clean up state
                    self.frida_process = None
                    self.current_script_name = None
                    self.process_monitor_task = None

                    # Clean up script file
                    if self.current_script_file and os.path.exists(
                        self.current_script_file
                    ):
                        try:
                            os.unlink(self.current_script_file)
                            self.current_script_file = None
                        except Exception as e:
                            logger.warning(f"Failed to clean up script file: {str(e)}")

                    await self.send_response(
                        {
                            "type": "frida",
                            "action": "script_stopped",
                            "script_name": script_name,
                            "message": f"Script '{script_name}' was already completed",
                        }
                    )
                    return

                # Cancel monitoring task before terminating
                if self.process_monitor_task and not self.process_monitor_task.done():
                    self.process_monitor_task.cancel()
                    logger.info("Cancelled process monitor task")

                # Terminate the process
                try:
                    self.frida_process.terminate()
                    logger.info(f"Sent SIGTERM to process")
                except ProcessLookupError:
                    logger.info(f"Process already terminated")
                    self.frida_process = None
                except Exception as e:
                    logger.warning(
                        f"Error terminating process: {str(e)} ({type(e).__name__})"
                    )

                # Wait for process to end with timeout
                if self.frida_process:
                    try:
                        await asyncio.wait_for(self.frida_process.wait(), timeout=5.0)
                        logger.info(f"Process terminated gracefully")
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Process did not terminate gracefully, forcing kill"
                        )
                        try:
                            # Force kill if it doesn't terminate gracefully
                            self.frida_process.kill()
                            await self.frida_process.wait()
                            logger.info(f"Process force killed")
                        except ProcessLookupError:
                            logger.info(f"Process already terminated during force kill")
                        except Exception as e:
                            logger.error(
                                f"Error force killing process: {str(e)} ({type(e).__name__})"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error waiting for process termination: {str(e)} ({type(e).__name__})"
                        )

                # Clean up state
                self.frida_process = None
                self.current_script_name = None
                self.process_monitor_task = None

                # Clean up script file
                if self.current_script_file and os.path.exists(
                    self.current_script_file
                ):
                    try:
                        os.unlink(self.current_script_file)
                        self.current_script_file = None
                        logger.info(f"Cleaned up script file")
                    except Exception as e:
                        logger.warning(
                            f"Failed to clean up script file: {str(e)} ({type(e).__name__})"
                        )

                await self.send_response(
                    {
                        "type": "frida",
                        "action": "script_stopped",
                        "script_name": script_name,
                        "message": f"Script '{script_name}' stopped",
                    }
                )
            else:
                logger.info(f"No script process to stop")
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

            # Get connection arguments
            connection_args = await self.get_frida_connection_args()

            # Try different possible paths for frida-ps
            frida_ps_paths = [
                "frida-ps",
                "/usr/local/bin/frida-ps",
                "/usr/bin/frida-ps",
            ]

            # Find working frida-ps command
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
                    else:
                        logger.debug(f"Failed to run {path}: {stderr.decode()}")
                except Exception as e:
                    logger.debug(f"Error testing {path}: {str(e)}")
                    continue

            if not cmd:
                await self.send_error("frida-ps not found or not working")
                return

            logger.info(f"Running frida-ps command: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                processes = []

                # Skip header line and parse process list
                lines = output.split("\n")
                if len(lines) > 1:  # Skip header
                    for line in lines[1:]:
                        if line.strip():
                            parts = line.strip().split(
                                None, 1
                            )  # Split on first whitespace
                            if len(parts) >= 2:
                                pid = parts[0]
                                name = parts[1]
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
            logger.error(f"Error listing processes: {str(e)}")
            await self.send_error(f"Error listing processes: {str(e)}")

    async def install_app(self, file_hash: str, app_name: str):
        """Install an APK file on the device"""
        try:
            logger.info(f"Installing app: {app_name} ({file_hash})")

            await self.send_response(
                {
                    "type": "frida",
                    "action": "app_install_start",
                    "app_name": app_name,
                    "file_hash": file_hash,
                }
            )

            # Import storage service to get file info
            from app.core.app_manager import AsyncStorageService

            storage = AsyncStorageService()

            # Get file info
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

            # Verify it's an APK file
            if file_info.get("file_type") != "apk":
                await self.send_response(
                    {
                        "type": "frida",
                        "action": "app_install_error",
                        "message": "File is not an APK",
                    }
                )
                return

            # Build file path
            storage_dir = "/shared_data"
            folder_path = file_info.get("folder_path")
            original_name = file_info.get("original_name")

            apk_path = os.path.join(storage_dir, folder_path, original_name)

            # Check if file exists
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

            # Install APK using ADB
            install_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.device_id,
                "install",
                "-r",
                apk_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await install_process.communicate()

            if install_process.returncode == 0:
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
                    stderr.decode().strip() if stderr else stdout.decode().strip()
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
            logger.info(f"Received Frida message: {data}")

            message = json.loads(data)
            if message.get("type") == "frida":
                await self.handle_frida_command(message)
            else:
                logger.warning(f"Unknown message type: {message.get('type')}")

        except json.JSONDecodeError:
            logger.error("Invalid JSON in Frida message")
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error handling Frida message: {str(e)}")
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
            logger.warning(f"Unknown Frida action: {action}")
            await self.send_error(f"Unknown action: {action}")

    async def send_response(self, data: Dict[str, Any]):
        """Send response to client"""
        try:
            if self.websocket.client_state.CONNECTED:
                await self.websocket.send_text(json.dumps(data))
            else:
                logger.warning("WebSocket not connected, cannot send response")
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")

    async def send_error(self, message: str):
        """Send error message"""
        await self.send_response(
            {"type": "frida", "action": "error", "message": message}
        )

    async def stop(self):
        """Stop Frida manager"""
        if not self.is_running:
            return

        self.is_running = False

        # Cancel process monitor task if running
        if self.process_monitor_task and not self.process_monitor_task.done():
            self.process_monitor_task.cancel()
            logger.info("Cancelled process monitor task")

        # Stop Frida process if running
        if self.frida_process:
            try:
                self.frida_process.terminate()
                await self.frida_process.wait()
            except:
                pass

        # Clean up state
        self.frida_process = None
        self.current_script_name = None
        self.process_monitor_task = None

        # Clean up script file
        if self.current_script_file and os.path.exists(self.current_script_file):
            try:
                os.unlink(self.current_script_file)
                self.current_script_file = None
            except:
                pass

        # Remove port forwarding only if we used it (localhost fallback)
        if self.frida_host == "localhost" and hasattr(self, "adb_forward_port"):
            await self.remove_port_forwarding()

        logger.info(f"Frida manager stopped for device {self.device_id}")

    async def _monitor_process_completion(self, script_name: str):
        """Monitor Frida process completion"""
        try:
            if not self.frida_process:
                return

            logger.info(f"Starting process monitor for script '{script_name}'")

            # Wait for process to complete
            returncode = await self.frida_process.wait()

            logger.info(f"Process completed with return code: {returncode}")

            # Clean up script file
            if self.current_script_file and os.path.exists(self.current_script_file):
                try:
                    os.unlink(self.current_script_file)
                    self.current_script_file = None
                    logger.info(f"Cleaned up script file")
                except Exception as e:
                    logger.warning(f"Failed to clean up script file: {str(e)}")

            # Reset state
            self.frida_process = None
            self.current_script_name = None
            self.process_monitor_task = None

            # Send completion notification
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
                        "message": f"Script '{script_name}' completed with errors (code: {returncode})",
                        "return_code": returncode,
                    }
                )

        except Exception as e:
            error_msg = (
                f"Error monitoring process completion: {str(e)} ({type(e).__name__})"
            )
            logger.error(error_msg)

            # Reset state even on error
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
