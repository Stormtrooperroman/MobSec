from typing import Dict, Optional, List
import asyncio
import logging
import os
from app.dynamic.device import Device


class DeviceManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DeviceManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.devices: Dict[str, Device] = {}
        self.logger = logging.getLogger(__name__)
        self.active_servers = {}

        asyncio.create_task(self._monitor_devices())

    async def _monitor_devices(self):
        """Continuous monitoring of connected devices"""
        while True:
            try:
                env = self._get_adb_env()
                process = await asyncio.create_subprocess_exec(
                    "adb",
                    "devices",
                    "-l",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    self.logger.error(f"Failed to get devices: {stderr.decode()}")
                    await asyncio.sleep(5)
                    continue

                current_devices = []
                lines = stdout.decode().split("\n")[1:]
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if (
                            len(parts) >= 2 and parts[1] == "device"
                        ):  # Only include ready devices
                            device = {
                                "udid": parts[0],
                                "status": parts[1],
                                "name": (
                                    parts[0] if len(parts) == 2 else " ".join(parts[2:])
                                ),
                            }
                            current_devices.append(device)

                await self._update_device_list(current_devices)

                await asyncio.sleep(5)  # Less frequent monitoring

            except Exception as e:
                self.logger.error(f"Error monitoring devices: {e}")
                await asyncio.sleep(5)

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
            else:
                self.devices[serial].state = device["status"]

    async def _init_adb(self):
        """
        Initializes the ADB server
        """
        try:
            # Just ensure ADB server is running
            env = self._get_adb_env()
            start_process = await asyncio.create_subprocess_exec(
                "adb",
                "start-server",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await start_process.communicate()

            if start_process.returncode != 0:
                self.logger.error(f"Failed to start ADB server: {stderr.decode()}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"Error initializing ADB: {str(e)}")
            return False

    def _get_adb_env(self):
        """Get environment variables for ADB commands"""
        from app.dynamic.emulator_manager import EmulatorManager

        env = EmulatorManager.get_adb_env()
        return env

    async def get_devices(self) -> List[Dict[str, str]]:
        """
        Gets the list of connected Android devices
        """
        try:
            env = self._get_adb_env()
            process = await asyncio.create_subprocess_exec(
                "adb",
                "devices",
                "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(f"Failed to get devices: {stderr.decode()}")
                return []

            raw_output = stdout.decode()

            devices = []
            lines = raw_output.split("\n")[1:]
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        device = {
                            "udid": parts[0],
                            "status": parts[1],
                            "name": (
                                parts[0] if len(parts) == 2 else " ".join(parts[2:])
                            ),
                        }
                        devices.append(device)

            return devices
        except Exception as e:
            self.logger.error(f"Error getting devices: {str(e)}")
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
                self.devices[device_id] = device
                return device

        self.logger.warning(f"Device '{device_id}' not found")
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
            self.logger.error(f"Error starting server: {str(e)}")
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
            self.logger.error(f"Error stopping server: {str(e)}")
            return False
