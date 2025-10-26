import os
from typing import Dict


def get_adb_env() -> Dict[str, str]:
    """Get environment variables for ADB commands"""
    return os.environ.copy()
