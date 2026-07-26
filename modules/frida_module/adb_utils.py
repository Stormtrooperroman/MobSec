"""ADB utilities for the Frida module."""

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
