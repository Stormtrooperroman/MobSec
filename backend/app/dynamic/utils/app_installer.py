import asyncio
import logging
import os
from typing import Tuple, Optional
from app.dynamic.utils.adb_utils import get_adb_env

logger = logging.getLogger(__name__)


class AppInstaller:
    """Class for installing applications on devices"""

    @staticmethod
    async def install_apk(
        device_id: str, apk_path: str, replace: bool = True
    ) -> Tuple[bool, str]:
        """
        Install APK on device

        Args:
            device_id: Device ID
            apk_path: Path to APK file
            replace: Replace existing application

        Returns:
            Tuple[success, message]
        """
        try:
            if not os.path.exists(apk_path):
                return False, f"APK file not found: {apk_path}"

            logger.info(f"Installing APK {apk_path} on device {device_id}")

            env = get_adb_env()
            cmd = ["adb", "-s", device_id, "install"]

            if replace:
                cmd.append("-r")

            cmd.append(apk_path)

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                success_msg = f"Successfully installed {os.path.basename(apk_path)}"
                logger.info(success_msg)
                return True, success_msg
            else:
                error_output = (
                    stderr.decode().strip() if stderr else stdout.decode().strip()
                )
                error_msg = (
                    f"Failed to install {os.path.basename(apk_path)}: {error_output}"
                )
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error installing APK: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    async def uninstall_apk(device_id: str, package_name: str) -> Tuple[bool, str]:
        """
        Uninstall application from device

        Args:
            device_id: Device ID
            package_name: Application package name

        Returns:
            Tuple[success, message]
        """
        try:
            logger.info(f"Uninstalling {package_name} from device {device_id}")

            env = get_adb_env()
            cmd = ["adb", "-s", device_id, "uninstall", package_name]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                success_msg = f"Successfully uninstalled {package_name}"
                logger.info(success_msg)
                return True, success_msg
            else:
                error_output = (
                    stderr.decode().strip() if stderr else stdout.decode().strip()
                )
                error_msg = f"Failed to uninstall {package_name}: {error_output}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error uninstalling APK: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
