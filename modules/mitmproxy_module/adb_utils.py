"""ADB utilities for the Mitmproxy module."""

import asyncio
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_adb_env() -> Dict[str, str]:
    return os.environ.copy()


async def execute_adb_command(
    device_id: str,
    command: List[str],
    env: Optional[Dict[str, str]] = None,
) -> tuple[str, str, int]:
    try:
        adb_cmd = ["adb", "-H", "backend"]
        if device_id:
            adb_cmd.extend(["-s", device_id])
        adb_cmd.extend(command)

        

        process = await asyncio.create_subprocess_exec(
            *adb_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await process.communicate()

        logger.info(stderr)
        return stdout.decode(), stderr.decode(), process.returncode
    except Exception as e:
        logger.error("Error executing ADB command: %s", str(e))
        return "", str(e), -1


async def execute_adb_shell(
    device_id: str,
    shell_command: str,
    env: Optional[Dict[str, str]] = None,
) -> tuple[str, str, int]:
    return await execute_adb_command(
        device_id=device_id,
        command=["shell", shell_command],
        env=env,
    )


async def remove_all_port_forwarding(
    device_id: Optional[str] = None,
) -> tuple[str, str, int]:
    return await execute_adb_command(
        device_id=device_id,
        command=["forward", "--remove-all"],
        env=None,
    )


async def check_su_availability(device_id: str) -> bool:
    """
    Check su availability on device

    Args:
        device_id: Device ID

    Returns:
        True if su is available, False otherwise
    """
    try:
        env = get_adb_env()

        # First check if su exists
        stdout, _, return_code = await execute_adb_shell(
            device_id=device_id,
            shell_command="which su",
            env=env,
        )

        if return_code != 0:
            logger.debug("su not found on device")
            return False

        # Check su functionality
        stdout, _, return_code = await execute_adb_shell(
            device_id=device_id,
            shell_command='echo "echo SU_WORKS" | timeout 5 su 2>/dev/null || echo "SU_FAILED"',
            env=env,
        )

        output = stdout.strip()

        if "SU_WORKS" in output:
            logger.debug("su is available and working")
            return True

        # Alternative check
        stdout, _, return_code = await execute_adb_shell(
            device_id=device_id,
            shell_command='echo "exit" | su 2>/dev/null && echo "SU_SIMPLE_WORKS" || echo "SU_SIMPLE_FAILED"',
            env=env,
        )
        simple_output = stdout.strip()

        available = "SU_SIMPLE_WORKS" in simple_output
        logger.debug("su availability: %s", available)
        return available

    except Exception as e:
        logger.error("Error checking su availability: %s", str(e))
        return False
