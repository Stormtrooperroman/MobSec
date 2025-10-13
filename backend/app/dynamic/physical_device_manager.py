import os
import logging
import asyncio
import subprocess
import re
from typing import Dict, List, Optional, Tuple
from app.dynamic.device import Device

logger = logging.getLogger(__name__)


class PhysicalDeviceManager:
    """Manager for physical Android devices connected via USB or WiFi"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.connected_devices: Dict[str, Dict] = {}
        self.adb_env = self._get_adb_env()
        
    def _get_adb_env(self) -> Dict[str, str]:
        """Get environment variables for ADB commands"""
        env = os.environ.copy()
        return env
    
    async def ensure_adb_server(self) -> bool:
        """Ensure ADB server is running"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", "start-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info("ADB server started successfully")
                return True
            else:
                self.logger.error(f"Failed to start ADB server: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting ADB server: {str(e)}")
            return False
    
    async def get_physical_devices(self) -> List[Dict[str, str]]:
        """Get list of connected physical devices"""
        try:
            await self.ensure_adb_server()
            
            process = await asyncio.create_subprocess_exec(
                "adb", "devices", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Failed to get devices: {stderr.decode()}")
                return []
            
            devices = []
            lines = stdout.decode().split('\n')[1:]
            
            for line in lines:
                if line.strip():
                    device_info = self._parse_device_line(line)
                    if device_info:
                        devices.append(device_info)
            
            return devices
            
        except Exception as e:
            self.logger.error(f"Error getting physical devices: {str(e)}")
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
            
            device_info = {
                "udid": udid,
                "status": status,
                "type": "physical",
                "connection": "usb"
            }
            
            if len(parts) > 2:
                device_props = " ".join(parts[2:])
                
                if "model:" in device_props:
                    model_match = re.search(r'model:([^\s]+)', device_props)
                    if model_match:
                        device_info["name"] = model_match.group(1)
                
                if "manufacturer:" in device_props:
                    manuf_match = re.search(r'manufacturer:([^\s]+)', device_props)
                    if manuf_match:
                        device_info["manufacturer"] = manuf_match.group(1)
                
                if "product:" in device_props:
                    product_match = re.search(r'product:([^\s]+)', device_props)
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
            self.logger.error(f"Error parsing device line '{line}': {str(e)}")
            return None
    
    async def connect_wifi_device(self, ip_address: str, port: int = 5555) -> bool:
        """Connect to a device via WiFi"""
        try:
            self.logger.info(f"Attempting to connect to device at {ip_address}:{port}")
            
            connect_cmd = ["adb", "connect", f"{ip_address}:{port}"]
            process = await asyncio.create_subprocess_exec(
                *connect_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Failed to connect to {ip_address}:{port}: {stderr.decode()}")
                return False
            
            await asyncio.sleep(2)
            
            devices = await self.get_physical_devices()
            for device in devices:
                if device["udid"] == f"{ip_address}:{port}":
                    self.logger.info(f"Successfully connected to WiFi device {ip_address}:{port}")
                    return True
            
            self.logger.warning(f"Device {ip_address}:{port} not found after connection attempt")
            return False
            
        except Exception as e:
            self.logger.error(f"Error connecting to WiFi device {ip_address}:{port}: {str(e)}")
            return False
    
    async def disconnect_wifi_device(self, ip_address: str, port: int = 5555) -> bool:
        """Disconnect from a WiFi device"""
        try:
            self.logger.info(f"Disconnecting from device at {ip_address}:{port}")
            
            disconnect_cmd = ["adb", "disconnect", f"{ip_address}:{port}"]
            process = await asyncio.create_subprocess_exec(
                *disconnect_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.logger.info(f"Successfully disconnected from {ip_address}:{port}")
                return True
            else:
                self.logger.warning(f"Disconnect command failed: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error disconnecting from WiFi device {ip_address}:{port}: {str(e)}")
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
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode()
                for line in output.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().strip('[]')
                        value = value.strip().strip('[]')
                        if key and value:
                            properties[key] = value
            
            info_cmd = ["adb", "-s", device_id, "shell", "cat", "/proc/cpuinfo"]
            try:
                process = await asyncio.create_subprocess_exec(
                    *info_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=self.adb_env
                )
                stdout, stderr = await process.communicate()
                if process.returncode == 0:
                    cpu_info = stdout.decode()
                    if "ARM" in cpu_info:
                        properties["architecture"] = "ARM"
                    elif "x86" in cpu_info:
                        properties["architecture"] = "x86"
            except:
                pass
            
            return properties
            
        except Exception as e:
            self.logger.error(f"Error getting device properties for {device_id}: {str(e)}")
            return {}
    
    async def check_device_connectivity(self, device_id: str) -> bool:
        """Check if a device is still connected and responsive"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell", "echo", "test",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            return process.returncode == 0
            
        except Exception as e:
            self.logger.error(f"Error checking device connectivity for {device_id}: {str(e)}")
            return False
    
    async def get_device_screen_info(self, device_id: str) -> Optional[Dict[str, int]]:
        """Get device screen dimensions"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb", "-s", device_id, "shell", "wm", "size",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                output = stdout.decode().strip()
                if "x" in output:
                    width, height = map(int, output.split("x"))
                    return {"width": width, "height": height}
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting screen info for {device_id}: {str(e)}")
            return None
    
    async def enable_wireless_debugging(self, device_id: str) -> bool:
        """Enable wireless debugging on a USB-connected device"""
        try:
            self.logger.info(f"Enabling wireless debugging on {device_id}")
            
            ip_cmd = ["adb", "-s", device_id, "shell", "ip", "route", "get", "1.1.1.1"]
            process = await asyncio.create_subprocess_exec(
                *ip_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Failed to get device IP: {stderr.decode()}")
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
            self.logger.info(f"Device IP address: {device_ip}")
            
            enable_cmd = ["adb", "-s", device_id, "tcpip", "5555"]
            process = await asyncio.create_subprocess_exec(
                *enable_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.adb_env
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.error(f"Failed to enable wireless debugging: {stderr.decode()}")
                return False
            
            await asyncio.sleep(3)
            
            if await self.connect_wifi_device(device_ip, 5555):
                self.logger.info(f"Successfully enabled wireless debugging on {device_id}")
                return True
            else:
                self.logger.error(f"Failed to connect via WiFi after enabling wireless debugging")
                return False
                
        except Exception as e:
            self.logger.error(f"Error enabling wireless debugging on {device_id}: {str(e)}")
            return False 