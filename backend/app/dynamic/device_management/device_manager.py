from typing import Dict, Optional, List, Set, Tuple
import asyncio
import logging
import os

from app.dynamic.device_management.scrcpy_device import ScrcpyDevice
from app.dynamic.device_management.physical_device_manager import PhysicalDeviceManager

# Hosts that, from the user's / frontend's point of view, mean "this machine".
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
DOCKER_HOST_ALIAS = os.getenv("DOCKER_HOST_ALIAS", "host.docker.internal")


class DeviceManager:
    _instance = None

    @staticmethod
    def split_address(
        device_id: str, default_port: Optional[int] = None
    ) -> Tuple[str, Optional[int]]:
        """'host:port' -> (host, port). Serials without a port -> (serial, default_port)."""
        host, sep, port = device_id.rpartition(":")
        if not sep:
            return device_id, default_port
        try:
            return host, int(port)
        except ValueError:
            return device_id, default_port

    @staticmethod
    def canonical_id(device_id: str) -> str:
        """Normalise any spelling of a local emulator id to '127.0.0.1:<port>'."""
        host, port = DeviceManager.split_address(device_id)
        if port is not None and (host in LOCAL_HOSTS or host == DOCKER_HOST_ALIAS):
            return f"127.0.0.1:{port}"
        return device_id

    @staticmethod
    def is_local_endpoint(device_id: str) -> bool:
        """True for devices published on the Docker host's loopback (emulators)."""
        return DeviceManager.canonical_id(device_id).startswith("127.0.0.1:")

    @staticmethod
    def get_connect_endpoint(
        device_id: str, default_port: Optional[int] = None
    ) -> Tuple[str, Optional[int]]:
        """(host, port) reachable from inside the container (SSH, raw sockets, ...)."""
        host, port = DeviceManager.split_address(device_id, default_port)
        if host in LOCAL_HOSTS:
            host = DOCKER_HOST_ALIAS
        return host, port

    @staticmethod
    def get_adb_address(device_id: str) -> str:
        """Value to pass to `adb -s` / scrcpy for this device from inside the container."""
        canonical = DeviceManager.canonical_id(device_id)
        if DeviceManager.is_local_endpoint(canonical):
            host, port = DeviceManager.get_connect_endpoint(canonical)
            return f"{host}:{port}"
        return device_id

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self._initialized = True
        self.devices: Dict[str, ScrcpyDevice] = {}
        self.logger = logging.getLogger(__name__)
        self.active_servers = {}
        self._pinned: Set[str] = set()
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
        """
        Get all devices from ADB.
        """
        return await self.physical_device_manager.get_physical_devices()

    async def _update_device_list(self, current_devices: List[Dict[str, str]]):
        """Updates the list of devices"""
        current = {self.canonical_id(d["udid"]): d for d in current_devices}

        disconnected = set(self.devices) - set(current) - self._pinned
        for serial in disconnected:
            await self.remove_device(serial)

        for serial, device in current.items():
            if serial not in self.devices:
                self.devices[serial] = ScrcpyDevice(
                    self.get_adb_address(serial), device["status"]
                )
                if "type" in device:
                    self.devices[serial].device_type = device["type"]
                if "name" in device:
                    self.devices[serial].display_name = device["name"]
            else:
                self.devices[serial].state = device["status"]

    async def get_devices(self) -> List[Dict[str, str]]:
        """
        Gets the list of all connected Android devices (emulators + physical)
        """
        try:
            return await self._get_all_devices()

        except Exception as e:
            self.logger.error("Error getting devices: %s", str(e))
            return []

    async def get_device(self, device_id: str) -> Optional[ScrcpyDevice]:
        """
        Gets information about a specific device
        """
        key = self.canonical_id(device_id)
        if key in self.devices:
            return self.devices[key]

        if self.is_local_endpoint(key):
            adb_address = self.get_adb_address(key)
            known = {self.canonical_id(d["udid"]) for d in await self.get_devices()}
            if key not in known:
                host, port = self.split_address(adb_address)
                if not await self.connect_wifi_device(host, port):
                    self.logger.warning("adb connect to %s failed", adb_address)
                    return None
            device = ScrcpyDevice(adb_address, "device")
            device.device_type = "emulator_android"
            self.devices[key] = device
            self._pinned.add(key)
            return device

        devices = await self.get_devices()

        for device_info in devices:
            if self.canonical_id(device_info["udid"]) == key:
                device = ScrcpyDevice(self.get_adb_address(key), device_info["status"])
                if "type" in device_info:
                    device.device_type = device_info["type"]
                if "name" in device_info:
                    device.display_name = device_info["name"]

                self.devices[key] = device
                return device

        self.logger.warning("Device '%s' not found", device_id)
        return None

    async def remove_device(self, serial: str):
        """Removes a device and stops all associated processes"""
        serial = self.canonical_id(serial)
        self._pinned.discard(serial)

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

            self.active_servers[self.canonical_id(device_id)] = result

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

            self.active_servers.pop(self.canonical_id(device_id), None)

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

    async def get_device_properties(self, device_id: str) -> Dict[str, str]:
        """Get detailed properties of a device"""
        return await self.physical_device_manager.get_device_properties(
            self.get_adb_address(device_id)
        )

    async def get_device_screen_info(self, device_id: str) -> Optional[Dict[str, int]]:
        """Get device screen dimensions"""
        return await self.physical_device_manager.get_device_screen_info(
            self.get_adb_address(device_id)
        )

    async def check_device_connectivity(self, device_id: str) -> bool:
        """Check if a device is still connected and responsive"""
        return await self.physical_device_manager.check_device_connectivity(
            self.get_adb_address(device_id)
        )

    async def pair_wifi_device(
        self, ip_address: str, port: int, pairing_port: int, pairing_code: str
    ):
        """Pair with a device via WiFi using adb pair (Android 11+ wireless debugging)"""
        return await self.physical_device_manager.pair_wifi_device(
            ip_address, port, pairing_port, pairing_code
        )
