import logging
import os
import asyncio
from typing import Tuple

from app.dynamic.utils.adb_utils import execute_adb_command

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

            logger.info("Installing APK %s on device %s", apk_path, device_id)

            cmd = ["install"]

            if replace:
                cmd.append("-r")

            cmd.append(apk_path)

            stdout, _, return_code = await execute_adb_command(
                device_id=device_id,
                command=cmd,
            )

            if return_code == 0:
                success_msg = f"Successfully installed {os.path.basename(apk_path)}"
                logger.info(success_msg)
                return True, success_msg

            error_output = stdout.strip()
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
            logger.info("Uninstalling %s from device %s", package_name, device_id)

            cmd = ["uninstall", package_name]

            stdout, _, return_code = await execute_adb_command(
                device_id=device_id,
                command=cmd,
            )

            if return_code == 0:
                success_msg = f"Successfully uninstalled {package_name}"
                logger.info(success_msg)
                return True, success_msg

            error_output = stdout.strip()
            error_msg = f"Failed to uninstall {package_name}: {error_output}"
            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Error uninstalling APK: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    async def install_rpm(
        device_id: str,
        rpm_path: str,
        replace: bool = True,
        emulator_subpath: str = None,
    ) -> Tuple[bool, str]:
        """
        Install RPM on Aurora OS device using SCP and rpm command

        Args:
            device_id: Device ID (format: host:port for SSH)
            rpm_path: Path to RPM file
            replace: Replace existing application
            emulator_subpath: Emulator subpath in shared_data volume for SSH key path

        Returns:
            Tuple[success, message]
        """
        try:
            if not os.path.exists(rpm_path):
                return False, f"RPM file not found: {rpm_path}"

            logger.info("Installing RPM %s on Aurora OS device %s", rpm_path, device_id)

            # Parse device_id to get host and port
            try:
                host, port = device_id.split(":")
                port = int(port)
            except ValueError:
                return (
                    False,
                    f"Invalid device_id format: {device_id}. Expected format: host:port",
                )

            # Map to host.docker.internal if localhost
            if host in {"localhost", "127.0.0.1"}:
                host = "host.docker.internal"

            rpm_filename = os.path.basename(rpm_path)
            remote_path = f"/tmp/{rpm_filename}"
            if not emulator_subpath:
                return False, "emulator_subpath is required for Aurora OS device"
            key_path = f"/shared_data/{emulator_subpath}/.adt-state/id_rsa"

            # Step 1: Copy RPM file to device via SCP
            logger.info("Copying RPM to device via SCP")
            scp_cmd = [
                "scp",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
                "-i",
                key_path,
                "-P",
                str(port),
                rpm_path,
                f"defaultuser@{host}:{remote_path}",
            ]

            scp_process = await asyncio.create_subprocess_exec(
                *scp_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            scp_stdout, scp_stderr = await scp_process.communicate()

            if scp_process.returncode != 0:
                error_output = scp_stderr.decode("utf-8", errors="replace")
                error_msg = f"Failed to copy RPM to device: {error_output}"
                logger.error(error_msg)
                return False, error_msg

            # Step 2: Install RPM via SSH
            logger.info("Installing RPM on device via SSH")

            # Build install command with devel-su for root access
            if replace:
                install_cmd = f"rpm -i --force {remote_path}"
            else:
                install_cmd = f"rpm -i {remote_path}"

            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
                "-i",
                key_path,
                "-p",
                str(port),
                f"defaultuser@{host}",
                install_cmd,
            ]

            ssh_process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            ssh_stdout, ssh_stderr = await ssh_process.communicate()
            ssh_stdout_str = ssh_stdout.decode("utf-8", errors="replace")
            ssh_stderr_str = ssh_stderr.decode("utf-8", errors="replace")

            if ssh_process.returncode == 0:
                success_msg = f"Successfully installed {rpm_filename}"
                logger.info(success_msg)

                # Step 3: Clean up temporary file
                await AppInstaller._cleanup_remote_file(
                    host, port, key_path, remote_path
                )

                return True, success_msg

            error_output = ssh_stderr_str or ssh_stdout_str
            error_msg = f"Failed to install RPM on device: {error_output}"
            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Error installing RPM: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    @staticmethod
    async def _cleanup_remote_file(
        host: str, port: int, key_path: str, remote_path: str
    ) -> None:
        """Clean up temporary file on remote device"""
        try:
            cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
                "-i",
                key_path,
                "-p",
                str(port),
                f"defaultuser@{host}",
                f"rm -f {remote_path}",
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            await process.communicate()
        except Exception as e:
            logger.warning("Failed to cleanup remote file %s: %s", remote_path, str(e))

    @staticmethod
    @staticmethod
    async def uninstall_rpm(
        device_id: str, package_name: str, emulator_subpath: str = None
    ) -> Tuple[bool, str]:
        """
        Uninstall application from Aurora OS device using SSH and rpm command

        Args:
            device_id: Device ID (format: host:port for SSH)
            package_name: Application package name
            emulator_subpath: Emulator subpath in shared_data volume for SSH key path

        Returns:
            Tuple[success, message]
        """
        try:
            logger.info(
                "Uninstalling %s from Aurora OS device %s", package_name, device_id
            )

            # Parse device_id to get host and port
            try:
                host, port = device_id.split(":")
                port = int(port)
            except ValueError:
                return (
                    False,
                    f"Invalid device_id format: {device_id}. Expected format: host:port",
                )

            # Map to host.docker.internal if localhost
            if host in {"localhost", "127.0.0.1"}:
                host = "host.docker.internal"

            if not emulator_subpath:
                return False, "emulator_subpath is required for Aurora OS device"
            key_path = f"/shared_data/{emulator_subpath}/.adt-state/id_rsa"

            # Build uninstall command with devel-su for root access
            uninstall_cmd = f"rpm -e {package_name}"

            ssh_cmd = [
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "UserKnownHostsFile=/dev/null",
                "-o",
                "LogLevel=ERROR",
                "-i",
                key_path,
                "-p",
                str(port),
                f"defaultuser@{host}",
                uninstall_cmd,
            ]

            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if process.returncode == 0:
                success_msg = f"Successfully uninstalled {package_name}"
                logger.info(success_msg)
                return True, success_msg

            error_output = stderr_str or stdout_str
            error_msg = f"Failed to uninstall {package_name}: {error_output}"
            logger.error(error_msg)
            return False, error_msg

        except Exception as e:
            error_msg = f"Error uninstalling RPM: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
