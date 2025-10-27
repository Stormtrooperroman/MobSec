import asyncio
import logging
from typing import Tuple, Optional
from app.dynamic.utils.adb_utils import get_adb_env

logger = logging.getLogger(__name__)


class ADBExecutor:
    """Class for executing ADB commands with unified handling"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.env = get_adb_env()

    async def execute(
        self, *args, timeout: Optional[float] = None
    ) -> Tuple[bytes, bytes, int]:
        """
        Universal method for executing ADB commands

        Args:
            *args: Arguments for adb command (without 'adb' and '-s device_id')
            timeout: Command execution timeout

        Returns:
            Tuple[stdout, stderr, returncode]
        """
        try:
            cmd = ["adb", "-s", self.device_id] + list(args)
            logger.debug("Executing ADB command: %s", " ".join(cmd))

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                raise TimeoutError(f"ADB command timed out after {timeout}s") from exc

            return stdout, stderr, process.returncode

        except Exception as e:
            logger.error("Error executing ADB command: %s", e)
            raise

    async def execute_shell(
        self, shell_command: str, timeout: Optional[float] = None
    ) -> Tuple[bytes, bytes, int]:
        """
        Execute shell command on device

        Args:
            shell_command: Command to execute in shell
            timeout: Command execution timeout

        Returns:
            Tuple[stdout, stderr, returncode]
        """
        return await self.execute("shell", shell_command, timeout=timeout)

    async def check_success(self, *args) -> bool:
        """
        Check command execution success

        Args:
            *args: Arguments for adb command

        Returns:
            True if command executed successfully (returncode == 0)
        """
        _, _, returncode = await self.execute(*args)
        return returncode == 0
