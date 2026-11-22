import logging
import subprocess
import asyncio
import os
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


class AuroraSSHClient:
    """SSH client for Aurora OS emulators"""

    def __init__(
        self,
        host: str,
        port: int,
        user: str = "defaultuser",
        emulator_subpath: Optional[str] = None,
        key_path: Optional[str] = None,
    ):
        """
        Initialize Aurora SSH client

        Args:
            host: Hostname or IP address
            port: SSH port (usually mapped from 2223)
            user: SSH username (default: defaultuser)
            emulator_subpath: Emulator subpath in shared_data volume (e.g., aurora_5_2_1_200)
            key_path: Explicit path to SSH private key (overrides emulator_subpath-based path)
        """
        self.host = host
        self.port = port
        self.user = user
        if key_path:
            self.key_path = key_path
        elif emulator_subpath:
            self.key_path = f"/shared_data/{emulator_subpath}/.adt-state/id_rsa"
        else:
            raise ValueError("Either emulator_subpath or key_path must be provided")

    def set_user(self, user: str):
        """Change SSH user"""
        self.user = user

    def _get_ssh_base_command(self, user: Optional[str] = None) -> List[str]:
        """Build base SSH command with common options"""
        ssh_user = user or self.user
        return [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "LogLevel=ERROR",
            "-i",
            self.key_path,
            "-p",
            str(self.port),
            f"{ssh_user}@{self.host}",
        ]

    async def execute_command(
        self, command: str, use_su: bool = False
    ) -> Dict[str, Any]:
        """
        Execute command on Aurora via SSH

        Args:
            command: Command to execute
            use_su: Whether to use devel-su for root access

        Returns:
            dict with stdout, stderr, and return code
        """
        try:
            if use_su:
                full_command = f"devel-su -c '{command}'"
            else:
                full_command = command

            ssh_cmd = self._get_ssh_base_command() + [full_command]

            process = await asyncio.create_subprocess_exec(
                *ssh_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            return {
                "stdout": stdout.decode("utf-8", errors="ignore"),
                "stderr": stderr.decode("utf-8", errors="ignore"),
                "returncode": process.returncode,
            }
        except Exception as e:
            logger.error("Failed to execute SSH command: %s", e)
            return {
                "stdout": "",
                "stderr": str(e),
                "returncode": 1,
            }

    async def execute_shell_command(self, command: str, use_su: bool = False) -> str:
        """Execute command and return stdout"""
        result = await self.execute_command(command, use_su)
        return result["stdout"]

    async def list_directory(
        self, path: str = "/", use_su: bool = False
    ) -> List[Dict[str, Any]]:
        """List directory contents"""
        try:
            cmd = f"ls -la {path}"
            result = await self.execute_command(cmd, use_su)

            if result["returncode"] != 0:
                error_msg = result["stderr"] or "Unknown error"
                logger.error("Failed to list directory %s: %s", path, error_msg)
                raise Exception(error_msg)

            lines = result["stdout"].strip().split("\n")
            entries = []

            for line in lines[1:]:  # Skip header line
                if not line.strip():
                    continue

                parts = line.split(maxsplit=8)
                if len(parts) >= 9:
                    permissions = parts[0]
                    name = parts[8]

                    # Skip . and ..
                    if name in (".", ".."):
                        continue

                    # Determine file type from permissions
                    is_directory = permissions.startswith("d")
                    is_symlink = permissions.startswith("l")

                    # Parse symlink target if present
                    target = None
                    if is_symlink and " -> " in name:
                        name, target = name.split(" -> ", 1)

                    # Determine type
                    if is_directory:
                        file_type = "directory"
                    elif is_symlink:
                        file_type = "symlink"
                    else:
                        file_type = "file"

                    entries.append(
                        {
                            "name": name,
                            "is_directory": is_directory,
                            "type": file_type,
                            "size": int(parts[4]) if parts[4].isdigit() else 0,
                            "modified": f"{parts[5]} {parts[6]} {parts[7]}",
                            "permissions": permissions,
                            "owner": parts[2],
                            "group": parts[3],
                            "target": target,
                        }
                    )

            return entries
        except Exception as e:
            logger.error("Error listing directory: %s", e)
            raise

    async def read_file(self, path: str, use_su: bool = False) -> Optional[str]:
        """Read file contents"""
        try:
            cmd = f"cat {path}"
            result = await self.execute_command(cmd, use_su)

            if result["returncode"] == 0:
                return result["stdout"]
            else:
                logger.warning("Failed to read file %s: %s", path, result["stderr"])
                return None
        except Exception as e:
            logger.error("Error reading file: %s", e)
            return None

    async def write_file(self, path: str, content: str, use_su: bool = False) -> bool:
        """Write content to file"""
        try:
            # Escape single quotes in content
            escaped_content = content.replace("'", "'\\''")
            cmd = f"cat > {path} << 'EOF'\n{escaped_content}\nEOF"
            result = await self.execute_command(cmd, use_su)

            return result["returncode"] == 0
        except Exception as e:
            logger.error("Error writing file: %s", e)
            return False

    async def check_connectivity(self) -> bool:
        """Check if SSH connection is available"""
        try:
            result = await self.execute_command("echo 'OK'")
            if result["returncode"] != 0:
                logger.error(
                    "Aurora SSH connectivity failed for %s:%s using key %s: %s",
                    self.host,
                    self.port,
                    self.key_path,
                    result["stderr"].strip(),
                )
            return result["returncode"] == 0
        except Exception:
            return False
