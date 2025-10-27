"""ADB utilities"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def get_adb_env() -> Dict[str, str]:
    """Get environment variables for ADB commands"""
    return os.environ.copy()


async def execute_adb_command(
    device_id: str,
    command: List[str],
    env: Optional[Dict[str, str]] = None,
) -> tuple[str, str, int]:
    """
    Execute ADB command and return stdout, stderr, and return code

    Args:
        device_id: Device serial or None for global command
        command: List of command parts (e.g., ["shell", "ls"])
        env: Optional environment variables

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    try:
        # Build full command
        adb_cmd = ["adb"]
        if device_id:
            adb_cmd.extend(["-s", device_id])
        adb_cmd.extend(command)

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
    env: Optional[Dict[str, str]] = None,
) -> tuple[str, str, int]:
    """
    Execute ADB shell command

    Args:
        device_id: Device serial
        shell_command: Shell command to execute
        env: Optional environment variables

    Returns:
        Tuple of (stdout, stderr, return_code)
    """
    return await execute_adb_command(
        device_id=device_id,
        command=["shell", shell_command],
        env=env,
    )


async def execute_adb_devices(env: Optional[Dict[str, str]] = None) -> tuple[str, str, int]:
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
        env=env,
    )


async def remove_all_port_forwarding(device_id: Optional[str] = None) -> tuple[str, str, int]:
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
        env=None,
    )


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
