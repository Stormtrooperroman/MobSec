import asyncio
import ipaddress
import logging
import re
from typing import Dict, List, Optional

from app.dynamic.utils.adb_utils import get_adb_env
from app.dynamic.utils.adb_utils import execute_adb_devices, execute_adb_shell, parse_devices_from_adb_output

logger = logging.getLogger(__name__)


class PhysicalDeviceManager:
    """Manager for physical Android devices connected via USB or WiFi"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.connected_devices: Dict[str, Dict] = {}
        self.adb_env = get_adb_env()
        self._adb_server_started = False

    async def ensure_adb_server(self) -> bool:
        """Ensure ADB server is running"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb",
                "start-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env,
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                self.logger.info("ADB server started successfully")
                return True

            self.logger.error("Failed to start ADB server: %s", stderr.decode())
            return False

        except Exception as e:
            self.logger.error("Error starting ADB server: %s", str(e))
            return False

    async def get_physical_devices(self) -> List[Dict[str, str]]:
        """Get list of connected physical devices"""
        try:
            # Ensure ADB server is running only once
            if not hasattr(self, "_adb_server_started"):
                await self.ensure_adb_server()
                self._adb_server_started = True

            
            stdout, _, return_code = await execute_adb_devices(env=self.adb_env)

            if return_code != 0:
                self.logger.error("Failed to get devices")
                return []

            devices = parse_devices_from_adb_output(
                stdout=stdout,
                parse_line_func=self._parse_device_line
            )

            return devices

        except Exception as e:
            self.logger.error("Error getting physical devices: %s", str(e))
            return []

    def _parse_device_line(self, line: str) -> Optional[Dict[str, str]]:
        """Parse a single device line from 'adb devices -l' output"""
        try:
            parts = line.split()
            if len(parts) < 2:
                return None

            udid = parts[0]
            status = parts[1]

            if status != "device":
                return None

            # Check if this is a Docker emulator by checking if it's in Docker network range
            device_type = "physical"
            connection = "usb"

            # Check for Docker emulator indicators
            if self._is_docker_emulator(udid, line):
                device_type = "emulator"
                connection = "docker"

            device_info = {
                "udid": udid,
                "status": status,
                "type": device_type,
                "connection": connection,
            }

            if len(parts) > 2:
                device_props = " ".join(parts[2:])

                if "model:" in device_props:
                    model_match = re.search(r"model:([^\s]+)", device_props)
                    if model_match:
                        device_info["name"] = model_match.group(1)

                if "manufacturer:" in device_props:
                    manuf_match = re.search(r"manufacturer:([^\s]+)", device_props)
                    if manuf_match:
                        device_info["manufacturer"] = manuf_match.group(1)

                if "product:" in device_props:
                    product_match = re.search(r"product:([^\s]+)", device_props)
                    if product_match:
                        device_info["product"] = product_match.group(1)

                if "name" not in device_info:
                    if "product" in device_info:
                        device_info["name"] = device_info["product"]
                    elif "manufacturer" in device_info:
                        device_info["name"] = f"{device_info['manufacturer']} Device"
                    else:
                        device_info["name"] = udid

            if "name" not in device_info:
                device_info["name"] = udid

            return device_info

        except Exception as e:
            self.logger.error("Error parsing device line '%s': %s", line, str(e))
            return None

    def _is_docker_emulator(self, udid: str, line: str) -> bool:
        """Check if device is a Docker emulator"""
        try:
            # Check for Docker network IP ranges (172.16.0.0/12, 192.168.0.0/16, 10.0.0.0/8)
            # Extract IP from UDID if it contains IP:port format
            if ":" in udid and "." in udid:
                ip_part = udid.split(":")[0]
                try:
                    ip = ipaddress.ip_address(ip_part)
                    # Check if IP is in Docker network ranges
                    docker_ranges = [
                        ipaddress.ip_network("172.16.0.0/12"),
                        ipaddress.ip_network("192.168.0.0/16"),
                        ipaddress.ip_network("10.0.0.0/8"),
                    ]

                    for network in docker_ranges:
                        if ip in network:
                            return True
                except ValueError:
                    pass

            # Check for emulator indicators in device properties
            emulator_indicators = [
                "emulator",
                "localhost",
                "127.0.0.1",
                "genymotion",
                "android_x86",
            ]
            line_lower = line.lower()

            for indicator in emulator_indicators:
                if indicator in line_lower:
                    return True

            return False

        except Exception as e:
            self.logger.error("Error checking if device is Docker emulator: %s", str(e))
            return False

    async def connect_wifi_device(self, ip_address: str, port: int = 5555) -> bool:
        """Connect to a device via WiFi"""
        try:
            self.logger.info(
                "Attempting to connect to device at %s:%s", ip_address, port
            )

            connect_cmd = ["adb", "connect", f"{ip_address}:{port}"]
            process = await asyncio.create_subprocess_exec(
                *connect_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(
                    "Failed to connect to %s:%s: %s",
                    ip_address,
                    port,
                    stderr.decode(),
                )
                return False

            await asyncio.sleep(2)

            devices = await self.get_physical_devices()
            for device in devices:
                if device["udid"] == f"{ip_address}:{port}":
                    self.logger.info(
                        "Successfully connected to WiFi device %s:%s",
                        ip_address,
                        port,
                    )
                    return True

            self.logger.warning(
                "Device %s:%s not found after connection attempt",
                ip_address,
                port,
            )
            return False

        except Exception as e:
            self.logger.error(
                "Error connecting to WiFi device %s:%s: %s",
                ip_address,
                port,
                str(e),
            )
            return False

    async def disconnect_wifi_device(self, ip_address: str, port: int = 5555) -> bool:
        """Disconnect from a WiFi device"""
        try:
            self.logger.info("Disconnecting from device at %s:%s", ip_address, port)

            disconnect_cmd = ["adb", "disconnect", f"{ip_address}:{port}"]
            process = await asyncio.create_subprocess_exec(
                *disconnect_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env,
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                self.logger.info(
                    "Successfully disconnected from %s:%s", ip_address, port
                )
                return True

            self.logger.warning("Disconnect command failed: %s", stderr.decode())
            return False

        except Exception as e:
            self.logger.error(
                "Error disconnecting from WiFi device %s:%s: %s",
                ip_address,
                port,
                str(e),
            )
            return False

    async def get_device_properties(self, device_id: str) -> Dict[str, str]:
        """Get detailed properties of a device"""
        try:
            properties = {}

            prop_cmd = ["adb", "-s", device_id, "shell", "getprop"]
            process = await asyncio.create_subprocess_exec(
                *prop_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode()
                for line in output.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().strip("[]")
                        value = value.strip().strip("[]")
                        if key and value:
                            properties[key] = value

            info_cmd = ["adb", "-s", device_id, "shell", "cat", "/proc/cpuinfo"]
            try:
                process = await asyncio.create_subprocess_exec(
                    *info_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self.adb_env,
                )
                stdout, _ = await process.communicate()
                if process.returncode == 0:
                    cpu_info = stdout.decode()
                    if "ARM" in cpu_info:
                        properties["architecture"] = "ARM"
                    elif "x86" in cpu_info:
                        properties["architecture"] = "x86"
            except Exception:
                pass

            return properties

        except Exception as e:
            self.logger.error(
                "Error getting device properties for %s: %s",
                device_id,
                str(e),
            )
            return {}

    async def check_device_connectivity(self, device_id: str) -> bool:
        """Check if a device is still connected and responsive"""
        try:
            
            _, _, return_code = await execute_adb_shell(
                device_id=device_id,
                shell_command="echo test",
                env=self.adb_env
            )

            return return_code == 0

        except Exception as e:
            self.logger.error(
                "Error checking device connectivity for %s: %s",
                device_id,
                str(e),
            )
            return False

    async def get_device_screen_info(self, device_id: str) -> Optional[Dict[str, int]]:
        """Get device screen dimensions"""
        try:
            stdout, _, return_code = await execute_adb_shell(
                device_id=device_id,
                shell_command="wm size",
                env=self.adb_env
            )

            if return_code == 0:
                output = stdout.decode().strip()
                if "x" in output:
                    width, height = map(int, output.split("x"))
                    return {"width": width, "height": height}

            return None

        except Exception as e:
            self.logger.error("Error getting screen info for %s: %s", device_id, str(e))
            return None

    async def enable_wireless_debugging(self, device_id: str) -> bool:
        """Enable wireless debugging on a USB-connected device"""
        try:
            self.logger.info("Enabling wireless debugging on %s", device_id)

            ip_cmd = ["adb", "-s", device_id, "shell", "ip", "route", "get", "1.1.1.1"]
            process = await asyncio.create_subprocess_exec(
                *ip_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error("Failed to get device IP: %s", stderr.decode())
                return False

            output = stdout.decode().strip()
            if "src" not in output:
                self.logger.error("Could not determine device IP address")
                return False

            parts = output.split()
            src_index = parts.index("src")
            if src_index + 1 >= len(parts):
                self.logger.error("Invalid IP route output format")
                return False

            device_ip = parts[src_index + 1]
            self.logger.info("Device IP address: %s", device_ip)

            enable_cmd = ["adb", "-s", device_id, "tcpip", "5555"]
            process = await asyncio.create_subprocess_exec(
                *enable_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(
                    "Failed to enable wireless debugging: %s",
                    stderr.decode(),
                )
                return False

            await asyncio.sleep(3)

            if await self.connect_wifi_device(device_ip, 5555):
                self.logger.info(
                    "Successfully enabled wireless debugging on %s",
                    device_id,
                )
                return True

            self.logger.error(
                "Failed to connect via WiFi after enabling wireless debugging"
            )
            return False

        except Exception as e:
            self.logger.error(
                "Error enabling wireless debugging on %s: %s",
                device_id,
                str(e),
            )
            return False
