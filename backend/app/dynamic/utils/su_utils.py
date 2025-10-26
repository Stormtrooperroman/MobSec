import asyncio
import logging
from app.dynamic.utils.adb_utils import get_adb_env

logger = logging.getLogger(__name__)


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
        which_process = await asyncio.create_subprocess_exec(
            "adb",
            "-s",
            device_id,
            "shell",
            "which su",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        which_stdout, which_stderr = await which_process.communicate()

        if which_process.returncode != 0:
            logger.debug("su not found on device")
            return False

        # Check su functionality
        test_process = await asyncio.create_subprocess_exec(
            "adb",
            "-s",
            device_id,
            "shell",
            'echo "echo SU_WORKS" | timeout 5 su 2>/dev/null || echo "SU_FAILED"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await test_process.communicate()

        output = stdout.decode("utf-8", errors="ignore").strip()

        if "SU_WORKS" in output:
            logger.debug("su is available and working")
            return True

        # Alternative check
        simple_process = await asyncio.create_subprocess_exec(
            "adb",
            "-s",
            device_id,
            "shell",
            'echo "exit" | su 2>/dev/null && echo "SU_SIMPLE_WORKS" || echo "SU_SIMPLE_FAILED"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        simple_stdout, simple_stderr = await simple_process.communicate()
        simple_output = simple_stdout.decode("utf-8", errors="ignore").strip()

        available = "SU_SIMPLE_WORKS" in simple_output
        logger.debug(f"su availability: {available}")
        return available

    except Exception as e:
        logger.error(f"Error checking su availability: {str(e)}")
        return False
