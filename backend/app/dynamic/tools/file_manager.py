import asyncio
import base64
import json
import logging
import os
from typing import Optional, Dict, Any

from fastapi import WebSocket

from app.dynamic.communication.base_websocket_manager import BaseWebSocketManager
from app.dynamic.utils.su_utils import check_su_availability
from app.dynamic.utils.adb_utils import execute_adb_shell, execute_adb_command


logger = logging.getLogger(__name__)


class FileManager(BaseWebSocketManager):
    def __init__(self, websocket: WebSocket, device_id: str):
        super().__init__(websocket, "file_manager")
        self.device_id = device_id
        self.is_running = False
        self.current_path = "/data/local/tmp"
        self.use_su = False
        self.su_available = False
        self.current_user = "unknown"

    async def start(self):
        """Starts the file manager"""
        if self.is_running:
            return True

        try:
            self.is_running = True

            await self.check_su_availability()

            await self.get_current_user()

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "ready",
                    "current_path": self.current_path,
                    "su_available": self.su_available,
                    "use_su": self.use_su,
                    "current_user": getattr(self, "current_user", "unknown"),
                }
            )

            await self.list_directory(self.current_path)

            return True

        except Exception as e:
            logger.error("Error starting file manager: %s", str(e))
            self.is_running = False
            return False

    async def check_su_availability(self):
        """Checks the availability of su on the device"""
        try:
            self.su_available = await check_su_availability(self.device_id)
        except Exception as e:
            logger.error("Error checking su availability: %s", str(e))
            self.su_available = False

    async def get_current_user(self):
        """Gets the current user"""
        try:
            command = "whoami" if not self.use_su else 'echo "whoami" | su'
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=command
            )

            if return_code == 0:
                self.current_user = stdout.strip()
            else:
                self.current_user = "unknown"

        except Exception as e:
            logger.error("Error getting current user: %s", str(e))
            self.current_user = "unknown"

    async def toggle_su(self):
        """Toggles the su mode"""
        if not self.su_available:
            await self.send_error("SU is not available on this device")
            return

        self.use_su = not self.use_su

        await self.get_current_user()

        await self.send_response(
            {
                "type": "file_manager",
                "action": "su_toggled",
                "use_su": self.use_su,
                "su_available": self.su_available,
                "current_user": getattr(self, "current_user", "unknown"),
            }
        )

    def get_shell_command(self, command: str) -> str:
        """Returns the command with su or without in depending on the settings"""
        if self.use_su and self.su_available:
            safe_command = command.replace('"', "'")
            return f'echo "{safe_command}" | su'
        return command

    async def handle_message(self, data: str):
        """Handles incoming messages from WebSocket"""
        try:

            try:
                message = json.loads(data)
                if message.get("type") == "file_manager":
                    await self.handle_file_command(message)
                else:
                    logger.warning("Unknown message type: %s", message.get("type"))
            except json.JSONDecodeError:
                logger.error("Invalid JSON in file manager message")
                await self.send_error("Invalid JSON format")

        except Exception as e:
            logger.error("Error handling file manager message: %s", str(e))
            await self.send_error(f"Error processing message: {str(e)}")

    async def handle_file_command(self, message: Dict[str, Any]):
        """Handles file manager commands"""
        action = message.get("action")

        if action == "list":
            await self.list_directory(message.get("path", self.current_path))
        elif action == "stat":
            await self.stat_file(message.get("path"))
        elif action == "download":
            await self.download_file(message.get("path"))
        elif action == "upload":
            await self.upload_file(message.get("path"), message.get("data"))
        elif action == "delete":
            await self.delete_file(message.get("path"))
        elif action == "mkdir":
            await self.create_directory(message.get("path"))
        elif action == "move":
            await self.move_file(message.get("source"), message.get("destination"))
        elif action == "copy":
            await self.copy_file(message.get("source"), message.get("destination"))
        elif action == "toggle_su":
            await self.toggle_su()
        else:
            logger.warning("Unknown file manager action: %s", action)
            await self.send_error(f"Unknown action: {action}")

    async def list_directory(self, path: str):
        """Gets the list of files and directories"""
        try:

            check_command = self.get_shell_command(
                f'test -d "{path}" && echo "DIR_EXISTS" || echo "NOT_DIR"'
            )

            check_output, check_error, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=check_command
            )

            check_output = check_output.strip()
            check_error = check_error.strip()

            if "NOT_DIR" in check_output or return_code != 0:
                error_msg = f"Path is not a directory or does not exist: {path}"
                if check_error:
                    error_msg += f" (Error: {check_error})"
                await self.send_error(error_msg)
                return

            ls_command = self.get_shell_command(f'ls -la "{path}" 2>/dev/null')

            stdout, stderr, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=ls_command
            )

            ls_output = stdout
            ls_error = stderr

            if return_code != 0:
                error_msg = f"Cannot access directory: {path}"
                if ls_error:
                    error_msg += f" (Error: {ls_error})"

                if self.use_su:
                    logger.warning(
                        "SU command failed for path %s, suggesting to disable SU mode", path
                    )
                    error_msg += " (Try disabling SU mode if the issue persists)"

                await self.send_error(error_msg)
                return

            entries = []
            lines = ls_output.strip().split("\n")

            for i, line in enumerate(lines):
                if not line.strip() or line.startswith("total"):
                    logger.debug("Skipping line %s (empty or total)", i)
                    continue

                entry = self.parse_ls_line(line)
                if entry:
                    entries.append(entry)
                else:
                    logger.debug("Failed to parse line %s: %s", i, repr(line))

            entries.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))

            self.current_path = path

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "list",
                    "path": path,
                    "entries": entries,
                }
            )

        except Exception as e:
            logger.error("Error listing directory %s: %s", path, str(e))
            await self.send_error(f"Error listing directory: {str(e)}")

    def parse_ls_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parses the output of ls -la"""
        try:
            logger.debug("Parsing ls line: %s", repr(line))

            parts = line.strip().split()
            if len(parts) < 8:
                logger.debug("Line has less than 8 parts: %s", len(parts))
                return None

            permissions = parts[0]
            links = parts[1]
            owner = parts[2]
            group = parts[3]
            size = parts[4]

            if len(parts) >= 8:
                name_parts = parts[7:]

                if permissions.startswith("l") and "->" in " ".join(name_parts):
                    full_name = " ".join(name_parts)
                    if " -> " in full_name:
                        name, target = full_name.split(" -> ", 1)
                    else:
                        name = full_name
                        target = None
                else:
                    name = " ".join(name_parts)
                    target = None

                date_time = " ".join(parts[5:7])
                if len(parts) > 7:
                    date_time += (
                        " " + parts[7] if ":" in parts[7] or parts[7].isdigit() else ""
                    )

            else:
                logger.debug("Line doesn't have enough parts for date/name")
                return None

            if name in [".", ".."]:
                logger.debug("Skipping directory entry: %s", name)
                return None

            file_type = "file"
            is_directory = False

            if permissions.startswith("d"):
                file_type = "directory"
                is_directory = True
            elif permissions.startswith("l"):
                file_type = "symlink"
            elif permissions.startswith("b"):
                file_type = "block_device"
            elif permissions.startswith("c"):
                file_type = "char_device"
            elif permissions.startswith("p"):
                file_type = "pipe"
            elif permissions.startswith("s"):
                file_type = "socket"

            try:
                file_size = int(size) if size.isdigit() else 0
            except ValueError:
                file_size = 0

            result = {
                "name": name.strip(),
                "type": file_type,
                "permissions": permissions,
                "owner": owner,
                "group": group,
                "size": file_size,
                "modified": date_time.strip(),
                "is_directory": is_directory,
                "links": links,
            }

            if target:
                result["target"] = target.strip()

            logger.debug("Successfully parsed: %s", result)
            return result

        except Exception as e:
            logger.error("Error parsing ls line '%s': %s", line, str(e))
            return None

    async def stat_file(self, path: str):
        """Gets detailed information about a file"""
        try:
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=f'stat "{path}" 2>/dev/null || echo "ERROR: Cannot stat file"'
            )

            if return_code != 0:
                await self.send_error(f"Cannot stat file: {path}")
                return

            output = stdout.decode("utf-8", errors="ignore")

            if "ERROR: Cannot stat file" in output:
                await self.send_error(f"Cannot stat file: {path}")
                return

            stat_info = self.parse_stat_output(output)

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "stat",
                    "path": path,
                    "stat": stat_info,
                }
            )

        except Exception as e:
            logger.error("Error getting file stats %s: %s", path, str(e))
            await self.send_error(f"Error getting file stats: {str(e)}")

    def parse_stat_output(self, output: str) -> Dict[str, Any]:
        """Parses the output of the stat command"""
        try:
            lines = output.strip().split("\n")
            stat_info = {}

            for line in lines:
                if "File:" in line:
                    stat_info["file"] = line.split("File:")[1].strip()
                elif "Size:" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "Size:":
                            stat_info["size"] = int(parts[i + 1])
                            break
                elif "Access:" in line and "Uid:" in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "Access:":
                            stat_info["permissions"] = parts[i + 1]
                            break
                elif "Modify:" in line:
                    stat_info["modified"] = line.split("Modify:")[1].strip()
                elif "Change:" in line:
                    stat_info["changed"] = line.split("Change:")[1].strip()
                elif "Birth:" in line:
                    stat_info["created"] = line.split("Birth:")[1].strip()

            return stat_info

        except Exception as e:
            logger.error("Error parsing stat output: %s", str(e))
            return {}

    async def download_file(self, path: str):
        """Downloads a file from the device"""
        try:

            check_command = self.get_shell_command(
                f'test -f "{path}" && echo "FILE" || echo "NOT_FILE"'
            )

            stdout, _, _ = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=check_command
            )

            if "NOT_FILE" in stdout:
                await self.send_error(f"Path is not a file: {path}")
                return

            temp_file = f"/tmp/download_{os.path.basename(path)}_{asyncio.get_event_loop().time()}"

            if self.use_su and self.su_available:
                filename = os.path.basename(path)
                timestamp = int(asyncio.get_event_loop().time())
                temp_device_path = (
                    f"/data/local/tmp/temp_download_{filename}_{timestamp}"
                )

                copy_command = self.get_shell_command(
                    f'cp "{path}" "{temp_device_path}" && chmod 644 "{temp_device_path}"'
                )
                _, stderr, return_code = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command=copy_command,
                )

                if return_code != 0:
                    await self.send_error(
                        f"Failed to copy file for download: {stderr}"
                    )
                    return

                _, _, return_code = await execute_adb_command(
                    device_id=self.device_id,
                    command=["pull", temp_device_path, temp_file],
                )

                cleanup_command = self.get_shell_command(f'rm "{temp_device_path}"')
                _, _, return_code = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command=cleanup_command,
                )
            else:
                _, _, return_code = await execute_adb_command(
                    device_id=self.device_id,
                    command=["pull", path, temp_file],
                )

            if return_code != 0:
                await self.send_error(f"Failed to download file: {stderr}")
                return

            try:
                with open(temp_file, "rb") as f:
                    file_data = f.read()

                encoded_data = base64.b64encode(file_data).decode("utf-8")

                await self.send_response(
                    {
                        "type": "file_manager",
                        "action": "download",
                        "path": path,
                        "filename": os.path.basename(path),
                        "size": len(file_data),
                        "data": encoded_data,
                    }
                )

            finally:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

        except Exception as e:
            logger.error("Error downloading file %s: %s", path, str(e))
            await self.send_error(f"Error downloading file: {str(e)}")

    async def upload_file(self, path: str, data: str):
        """Uploads a file to the device"""
        try:
            file_data = base64.b64decode(data)

            temp_file = f"/tmp/upload_{os.path.basename(path)}_{asyncio.get_event_loop().time()}"

            try:
                with open(temp_file, "wb") as f:
                    f.write(file_data)

                _, stderr, return_code = await execute_adb_command(
                    device_id=self.device_id,
                    command=["push", temp_file, path],
                )

                if return_code != 0:
                    await self.send_error(f"Failed to upload file: {stderr}")
                    return

                await self.send_response(
                    {
                        "type": "file_manager",
                        "action": "upload",
                        "path": path,
                        "success": True,
                    }
                )

            finally:
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

        except Exception as e:
            logger.error("Error uploading file %s: %s", path, str(e))
            await self.send_error(f"Error uploading file: {str(e)}")

    async def delete_file(self, path: str):
        """Deletes a file or directory"""
        try:
            logger.debug("Deleting: %s", path)

            rm_command = self.get_shell_command(
                f'rm -rf "{path}" && echo "SUCCESS" || echo "FAILED"'
            )
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=rm_command
            )

            if "FAILED" in stdout or return_code != 0:
                await self.send_error(f"Failed to delete: {path}")
                return

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "delete",
                    "path": path,
                    "success": True,
                }
            )

        except Exception as e:
            logger.error("Error deleting %s: %s", path, str(e))
            await self.send_error(f"Error deleting: {str(e)}")

    async def create_directory(self, path: str):
        """Creates a directory"""
        try:
            logger.debug("Creating directory: %s", path)

            mkdir_command = self.get_shell_command(
                f'mkdir -p "{path}" && echo "SUCCESS" || echo "FAILED"'
            )
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=mkdir_command
            )

            if "FAILED" in stdout or return_code != 0:
                await self.send_error(f"Failed to create directory: {path}")
                return

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "mkdir",
                    "path": path,
                    "success": True,
                }
            )

        except Exception as e:
            logger.error("Error creating directory %s: %s", path, str(e))
            await self.send_error(f"Error creating directory: {str(e)}")

    async def move_file(self, source: str, destination: str):
        """Moves a file or directory"""
        try:
            logger.debug("Moving %s to %s", source, destination)

            mv_command = self.get_shell_command(
                f'mv "{source}" "{destination}" && echo "SUCCESS" || echo "FAILED"'
            )
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=mv_command,
            )

            if "FAILED" in stdout or return_code != 0:
                await self.send_error(f"Failed to move {source} to {destination}")
                return

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "move",
                    "source": source,
                    "destination": destination,
                    "success": True,
                }
            )

        except Exception as e:
            logger.error("Error moving %s to %s: %s", source, destination, str(e))
            await self.send_error(f"Error moving file: {str(e)}")

    async def copy_file(self, source: str, destination: str):
        """Copies a file or directory"""
        try:
            logger.debug("Copying %s to %s", source, destination)

            cp_command = self.get_shell_command(
                f'cp -r "{source}" "{destination}" && echo "SUCCESS" || echo "FAILED"'
            )
            stdout, _, return_code = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=cp_command,
            )

            if "FAILED" in stdout or return_code != 0:
                await self.send_error(f"Failed to copy {source} to {destination}")
                return

            await self.send_response(
                {
                    "type": "file_manager",
                    "action": "copy",
                    "source": source,
                    "destination": destination,
                    "success": True,
                }
            )

        except Exception as e:
            logger.error("Error copying %s to %s: %s", source, destination, str(e))
            await self.send_error(f"Error copying file: {str(e)}")

    async def stop(self):
        """Stops the file manager"""
        if not self.is_running:
            return

        self.is_running = False
