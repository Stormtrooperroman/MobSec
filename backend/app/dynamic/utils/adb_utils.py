"""ADB utilities"""

import os
import asyncio
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_adb_env() -> Dict[str, str]:
    """Get environment variables for ADB commands"""
    return os.environ.copy()


async def execute_adb_command(
    device_id: str,
    command: List[str],
) -> tuple[str, str, int]:
    """
    Execute ADB command and return stdout, stderr, and return code

    Args:
        device_id: Device serial or None for global command
        command: List of command parts (e.g., ["shell", "ls"])

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    try:
        # Build full command
        adb_cmd = ["adb"]
        if device_id:
            adb_cmd.extend(["-s", device_id])
        adb_cmd.extend(command)

        env = get_adb_env()

        # Execute command
        process = await asyncio.create_subprocess_exec(
            *adb_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await process.communicate()
        return stdout.decode(), stderr.decode(), process.returncode

    except Exception as e:
        logger.error("Error executing ADB command: %s", str(e))
        return "", str(e), -1


async def execute_adb_shell(
    device_id: str,
    shell_command: str,
) -> tuple[str, str, int]:
    """
    Execute ADB shell command

    Args:
        device_id: Device serial
        shell_command: Shell command to execute

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    return await execute_adb_command(
        device_id=device_id,
        command=["shell", shell_command],
    )


async def execute_adb_devices() -> tuple[str, str, int]:
    """
    Get list of connected devices

    Args:
        env: Optional environment variables

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    return await execute_adb_command(
        device_id=None,
        command=["devices", "-l"],
    )


async def remove_all_port_forwarding(
    device_id: Optional[str] = None,
) -> tuple[str, str, int]:
    """
    Remove all port forwarding for a device or globally

    Args:
        device_id: Device serial or None for global

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    return await execute_adb_command(
        device_id=device_id,
        command=["forward", "--remove-all"],
    )


async def is_adb_server_running(host: str = "127.0.0.1", port: int = 5037) -> bool:
    """
    Check whether the ADB server is currently listening on its default port.

    Args:
        host: Host where the ADB server is expected to listen.
        port: Port where the ADB server is expected to listen.

    Returns:
        True if a connection to the ADB server port succeeds, False otherwise.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=1.0
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False


async def ensure_adb_server() -> bool:
    """
    Ensure ADB server is running, starting it if needed.

    Returns:
        True if server is already running or started successfully, False otherwise.
    """
    try:
        if await is_adb_server_running():
            logger.info("ADB server is already running")
            return True

        env = get_adb_env()

        cmd: List[str] = ["adb", "-a", "server", "start"]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info("ADB server started successfully")
            return True

        logger.error("Failed to start ADB server adb utils: %s", stderr.decode())
        return False

    except Exception as e:
        logger.error("Error starting ADB server: %s", str(e))
        return False


def parse_devices_from_adb_output(stdout: str, parse_line_func) -> list:
    """
    Parse devices list from ADB 'devices -l' output

    Args:
        stdout: Output from ADB command
        parse_line_func: Function to parse a single device line

    Returns:
        List of device info dictionaries
    """
    devices = []
    lines = stdout.split("\n")[1:]

    for line in lines:
        if line.strip():
            device_info = parse_line_func(line)
            if device_info:
                devices.append(device_info)

    return devices
