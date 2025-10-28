import logging
from app.dynamic.utils.adb_utils import get_adb_env, execute_adb_shell

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
