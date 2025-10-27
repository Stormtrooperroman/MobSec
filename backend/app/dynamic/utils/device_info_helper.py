import asyncio
import logging
from typing import Optional
from app.dynamic.utils.adb_utils import get_adb_env
from app.dynamic.utils.adb_utils import execute_adb_shell

logger = logging.getLogger(__name__)


class DeviceInfoHelper:
    """Class for getting device information"""

    @staticmethod
    async def get_device_ip(device_id: str) -> Optional[str]:
        """
        Get device IP address

        Args:
            device_id: Device ID

        Returns:
            Device IP address or None
        """
        try:
            env = get_adb_env()

            # Method 1: Get IP via ip route
            cmd = f"adb -s {device_id} shell ip route get 1.1.1.1"
            process = await asyncio.create_subprocess_exec(
                *cmd.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                if "src" in output:
                    parts = output.split()
                    src_index = parts.index("src")
                    if src_index + 1 < len(parts):
                        device_ip = parts[src_index + 1]
                        logger.info("Device IP: %s", device_ip)
                        return device_ip

            # Method 2: Get IP via ifconfig
            interfaces = ["wlan0", "eth0", "eth1", "wlan1"]

            for interface in interfaces:
                try:
                    
                    cmd = (
                        f"ip addr show {interface} | grep 'inet ' "
                        f"| head -1 | awk '{{print $2}}' | cut -d'/' -f1"
                    )
                    stdout, _, return_code = await execute_adb_shell(
                        device_id=device_id,
                        shell_command=cmd,
                        env=env
                    )

                    if return_code == 0:
                        ip = stdout.strip()
                        if ip and ip != "127.0.0.1" and not ip.startswith("169.254"):
                            logger.info("Device IP from %s: %s", interface, ip)
                            return ip

                except Exception as e:
                    logger.debug("Failed to get IP from %s: %s", interface, str(e))
                    continue

            logger.warning("Could not determine device IP")
            return None

        except Exception as e:
            logger.error("Error getting device IP: %s", str(e))
            return None

    @staticmethod
    def is_valid_ip(ip: str) -> bool:
        """
        Validate IP address

        Args:
            ip: IP address to validate

        Returns:
            True if IP is valid
        """
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
