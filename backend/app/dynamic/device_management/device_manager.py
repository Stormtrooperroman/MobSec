from typing import Dict, Optional, List
import asyncio
import logging

from app.dynamic.device_management.device import Device
from app.dynamic.device_management.physical_device_manager import PhysicalDeviceManager
from app.dynamic.utils.adb_utils import get_adb_env
from app.dynamic.utils.adb_utils import execute_adb_devices, parse_devices_from_adb_output


class DeviceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self.devices: Dict[str, Device] = {}
        self.logger = logging.getLogger(__name__)
        self.active_servers = {}
        self.physical_device_manager = PhysicalDeviceManager()

        asyncio.create_task(self._monitor_devices())

    async def _monitor_devices(self):
        """Continuous monitoring of connected devices (both emulators and physical)"""
        while True:
            try:
                # Get all devices from ADB
                all_devices = await self._get_all_devices()

                await self._update_device_list(all_devices)

                await asyncio.sleep(5)

            except Exception as e:
                self.logger.error("Error monitoring devices: %s", e)
                await asyncio.sleep(5)

    async def _get_all_devices(self) -> List[Dict[str, str]]:
        """Get all devices from ADB with proper type classification"""
        try:
            env = get_adb_env()

            stdout, stderr, return_code = await execute_adb_devices(env=env)

            if return_code != 0:
                self.logger.error("Failed to get devices: %s", stderr)
                return []

            devices = parse_devices_from_adb_output(
                stdout=stdout,
                parse_line_func=self.physical_device_manager._parse_device_line
            )

            return devices

        except Exception as e:
            self.logger.error("Error getting all devices: %s", str(e))
            return []

    async def _update_device_list(self, current_devices: List[Dict[str, str]]):
        """Updates the list of devices"""
        disconnected = set(self.devices.keys()) - set(
            device["udid"] for device in current_devices
        )
        for serial in disconnected:
            await self.remove_device(serial)

        for device in current_devices:
            serial = device["udid"]
            if serial not in self.devices:
                self.devices[serial] = Device(serial, device["status"])
                if "type" in device:
                    self.devices[serial].device_type = device["type"]
                if "name" in device:
                    self.devices[serial].display_name = device["name"]
            else:
                self.devices[serial].state = device["status"]

    async def _init_adb(self):
        """
        Initializes the ADB server
        """
        try:
            env = get_adb_env()
            start_process = await asyncio.create_subprocess_exec(
                "adb",
                "start-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            _, stderr = await start_process.communicate()

            if start_process.returncode != 0:
                self.logger.error("Failed to start ADB server: %s", stderr.decode())
                return False

            return True

        except Exception as e:
            self.logger.error("Error initializing ADB: %s", str(e))
            return False

    async def get_devices(self) -> List[Dict[str, str]]:
        """
        Gets the list of all connected Android devices (emulators + physical)
        """
        try:
            return await self._get_all_devices()

        except Exception as e:
            self.logger.error("Error getting devices: %s", str(e))
            return []

    async def get_device(self, device_id: str) -> Optional[Device]:
        """
        Gets information about a specific device
        """
        if device_id in self.devices:
            return self.devices[device_id]

        devices = await self.get_devices()

        for device_info in devices:
            if device_info["udid"] == device_id:
                device = Device(device_info["udid"], device_info["status"])
                if "type" in device_info:
                    device.device_type = device_info["type"]
                if "name" in device_info:
                    device.display_name = device_info["name"]

                self.devices[device_id] = device
                return device

        self.logger.warning("Device '%s' not found", device_id)
        return None

    async def remove_device(self, serial: str):
        """Removes a device and stops all associated processes"""
        if serial in self.devices:
            device = self.devices[serial]
            await device.kill_server()
            del self.devices[serial]

        if serial in self.active_servers:
            del self.active_servers[serial]

    async def start_device_server(self, device_id: str) -> Dict:
        """
        Starts the scrcpy server on the specified device
        """
        try:
            device = await self.get_device(device_id)
            if not device:
                return None

            result = await device.start_server()
            if result is None:
                return None

            self.active_servers[device_id] = result

            return {
                "status": "success",
                "message": "Server started successfully",
                "data": result,
            }

        except Exception as e:
            self.logger.error("Error starting server: %s", str(e))
            return None

    async def stop_device_server(self, device_id: str) -> bool:
        """
        Stops the scrcpy server on the specified device
        """
        try:
            device = await self.get_device(device_id)
            if device:
                await device.kill_server()

            if device_id in self.active_servers:
                del self.active_servers[device_id]

            return True
        except Exception as e:
            self.logger.error("Error stopping server: %s", str(e))
            return False

    async def connect_wifi_device(self, ip_address: str, port: int = 5555) -> bool:
        """Connect to a device via WiFi"""
        return await self.physical_device_manager.connect_wifi_device(ip_address, port)

    async def disconnect_wifi_device(self, ip_address: str, port: int = 5555) -> bool:
        """Disconnect from a WiFi device"""
        return await self.physical_device_manager.disconnect_wifi_device(
            ip_address, port
        )

    async def enable_wireless_debugging(self, device_id: str) -> bool:
        """Enable wireless debugging on a USB-connected device"""
        return await self.physical_device_manager.enable_wireless_debugging(device_id)

    async def get_device_properties(self, device_id: str) -> Dict[str, str]:
        """Get detailed properties of a device"""
        return await self.physical_device_manager.get_device_properties(device_id)

    async def get_device_screen_info(self, device_id: str) -> Optional[Dict[str, int]]:
        """Get device screen dimensions"""
        return await self.physical_device_manager.get_device_screen_info(device_id)

    async def check_device_connectivity(self, device_id: str) -> bool:
        """Check if a device is still connected and responsive"""
        return await self.physical_device_manager.check_device_connectivity(device_id)
