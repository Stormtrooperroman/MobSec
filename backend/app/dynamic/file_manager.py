import asyncio
import json
import logging
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import WebSocket
import subprocess

logger = logging.getLogger(__name__)

class FileManager:
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.is_running = False
        self.current_path = "/data/local/tmp"
        self.use_su = False
        self.su_available = False

    async def start(self):
        """Starts the file manager"""
        if self.is_running:
            return True
            
        try:
            self.is_running = True
            logger.info(f"Starting file manager for device {self.device_id}")
            
            await self.check_su_availability()
            
            await self.get_current_user()
            
            await self.send_response({
                "type": "file_manager",
                "action": "ready",
                "current_path": self.current_path,
                "su_available": self.su_available,
                "use_su": self.use_su,
                "current_user": getattr(self, 'current_user', 'unknown')
            })
            
            await self.list_directory(self.current_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting file manager: {str(e)}")
            self.is_running = False
            return False

    async def check_su_availability(self):
        """Checks the availability of su on the device"""
        try:
            logger.info(f"Checking SU availability for device {self.device_id}")
            
            which_process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', 
                'which su',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            which_stdout, which_stderr = await which_process.communicate()
            
            logger.info(f"which su result: {which_stdout.decode().strip()}")
            
            if which_process.returncode != 0:
                logger.info("su binary not found")
                self.su_available = False
                return
            
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', 
                'echo "echo SU_WORKS" | timeout 5 su 2>/dev/null || echo "SU_FAILED"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            output = stdout.decode('utf-8', errors='ignore').strip()
            logger.info(f"SU test output: '{output}'")
            logger.info(f"SU test stderr: '{stderr.decode().strip()}'")
            
            if "SU_WORKS" in output:
                self.su_available = True
            else:
                logger.info("Primary SU test failed, trying simple su test")
                simple_process = await asyncio.create_subprocess_exec(
                    'adb', '-s', self.device_id, 'shell', 
                    'echo "exit" | su 2>/dev/null && echo "SU_SIMPLE_WORKS" || echo "SU_SIMPLE_FAILED"',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                simple_stdout, simple_stderr = await simple_process.communicate()
                simple_output = simple_stdout.decode('utf-8', errors='ignore').strip()
                
                logger.info(f"Simple SU test output: '{simple_output}'")
                self.su_available = "SU_SIMPLE_WORKS" in simple_output
            
            logger.info(f"SU availability for device {self.device_id}: {self.su_available}")
            
        except Exception as e:
            logger.error(f"Error checking su availability: {str(e)}")
            self.su_available = False

    async def get_current_user(self):
        """Gets the current user"""
        try:
            command = 'whoami' if not self.use_su else 'echo "whoami" | su'
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.current_user = stdout.decode('utf-8', errors='ignore').strip()
            else:
                self.current_user = 'unknown'
                
            logger.info(f"Current user for device {self.device_id}: {self.current_user}")
            
        except Exception as e:
            logger.error(f"Error getting current user: {str(e)}")
            self.current_user = 'unknown'

    async def toggle_su(self):
        """Toggles the su mode"""
        if not self.su_available:
            await self.send_error("SU is not available on this device")
            return
            
        self.use_su = not self.use_su
        logger.info(f"SU mode toggled for device {self.device_id}: {self.use_su}")
        
        await self.get_current_user()
        
        await self.send_response({
            "type": "file_manager",
            "action": "su_toggled",
            "use_su": self.use_su,
            "su_available": self.su_available,
            "current_user": getattr(self, 'current_user', 'unknown')
        })

    def get_shell_command(self, command: str) -> str:
        """Returns the command with su or without in depending on the settings"""
        if self.use_su and self.su_available:
            safe_command = command.replace('"', "'")
            return f'echo "{safe_command}" | su'
        else:
            return command

    async def handle_message(self, data: str):
        """Handles incoming messages from WebSocket"""
        try:
            logger.info(f"Received file manager message: {data}")
            
            try:
                message = json.loads(data)
                if message.get('type') == 'file_manager':
                    await self.handle_file_command(message)
                else:
                    logger.warning(f"Unknown message type: {message.get('type')}")
            except json.JSONDecodeError:
                logger.error("Invalid JSON in file manager message")
                await self.send_error("Invalid JSON format")
                
        except Exception as e:
            logger.error(f"Error handling file manager message: {str(e)}")
            await self.send_error(f"Error processing message: {str(e)}")

    async def handle_file_command(self, message: Dict[str, Any]):
        """Handles file manager commands"""
        action = message.get('action')
        
        if action == 'list':
            await self.list_directory(message.get('path', self.current_path))
        elif action == 'stat':
            await self.stat_file(message.get('path'))
        elif action == 'download':
            await self.download_file(message.get('path'))
        elif action == 'upload':
            await self.upload_file(message.get('path'), message.get('data'))
        elif action == 'delete':
            await self.delete_file(message.get('path'))
        elif action == 'mkdir':
            await self.create_directory(message.get('path'))
        elif action == 'move':
            await self.move_file(message.get('source'), message.get('destination'))
        elif action == 'copy':
            await self.copy_file(message.get('source'), message.get('destination'))
        elif action == 'toggle_su':
            await self.toggle_su()
        else:
            logger.warning(f"Unknown file manager action: {action}")
            await self.send_error(f"Unknown action: {action}")

    async def list_directory(self, path: str):
        """Gets the list of files and directories"""
        try:
            logger.info(f"Listing directory: {path} (SU mode: {self.use_su})")
            
            check_command = self.get_shell_command(f'test -d "{path}" && echo "DIR_EXISTS" || echo "NOT_DIR"')
            logger.info(f"Check command: {check_command}")
            
            check_process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', check_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            check_stdout, check_stderr = await check_process.communicate()
            
            check_output = check_stdout.decode().strip()
            check_error = check_stderr.decode().strip()
            
            logger.info(f"Check result: stdout='{check_output}', stderr='{check_error}', returncode={check_process.returncode}")
            
            if "NOT_DIR" in check_output or check_process.returncode != 0:
                error_msg = f"Path is not a directory or does not exist: {path}"
                if check_error:
                    error_msg += f" (Error: {check_error})"
                await self.send_error(error_msg)
                return
            
            ls_command = self.get_shell_command(f'ls -la "{path}" 2>/dev/null')
            logger.info(f"LS command: {ls_command}")
            
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', ls_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            ls_output = stdout.decode('utf-8', errors='ignore')
            ls_error = stderr.decode('utf-8', errors='ignore')
            
            logger.info(f"LS result: returncode={process.returncode}, stdout_len={len(ls_output)}, stderr='{ls_error}'")
            
            if process.returncode != 0:
                error_msg = f"Cannot access directory: {path}"
                if ls_error:
                    error_msg += f" (Error: {ls_error})"
                
                if self.use_su:
                    logger.warning(f"SU command failed for path {path}, suggesting to disable SU mode")
                    error_msg += " (Try disabling SU mode if the issue persists)"
                
                await self.send_error(error_msg)
                return
                
            entries = []
            lines = ls_output.strip().split('\n')
            
            logger.info(f"LS output lines: {len(lines)}")
            logger.info(f"LS raw output: {repr(ls_output)}")
            
            for i, line in enumerate(lines):
                logger.info(f"Line {i}: {repr(line)}")
                if not line.strip() or line.startswith('total'):
                    logger.info(f"Skipping line {i} (empty or total)")
                    continue
                    
                entry = self.parse_ls_line(line)
                if entry:
                    entries.append(entry)
                    logger.info(f"Parsed entry: {entry}")
                else:
                    logger.warning(f"Failed to parse line {i}: {repr(line)}")
            
            entries.sort(key=lambda x: (not x['is_directory'], x['name'].lower()))
            
            self.current_path = path
            
            logger.info(f"Successfully listed {len(entries)} entries in {path}")
            
            await self.send_response({
                "type": "file_manager",
                "action": "list",
                "path": path,
                "entries": entries
            })
            
        except Exception as e:
            logger.error(f"Error listing directory {path}: {str(e)}")
            await self.send_error(f"Error listing directory: {str(e)}")

    def parse_ls_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parses the output of ls -la"""
        try:
            logger.debug(f"Parsing ls line: {repr(line)}")
            
            parts = line.strip().split()
            if len(parts) < 8:
                logger.debug(f"Line has less than 8 parts: {len(parts)}")
                return None
                
            permissions = parts[0]
            links = parts[1]
            owner = parts[2]
            group = parts[3]
            size = parts[4]
            
            if len(parts) >= 8:
                name_parts = parts[7:]
                
                if permissions.startswith('l') and '->' in ' '.join(name_parts):
                    full_name = ' '.join(name_parts)
                    if ' -> ' in full_name:
                        name, target = full_name.split(' -> ', 1)
                    else:
                        name = full_name
                        target = None
                else:
                    name = ' '.join(name_parts)
                    target = None
                
                date_time = ' '.join(parts[5:7])
                if len(parts) > 7:
                    date_time += ' ' + parts[7] if ':' in parts[7] or parts[7].isdigit() else ''
                
            else:
                logger.debug(f"Line doesn't have enough parts for date/name")
                return None
            
            if name in ['.', '..']:
                logger.debug(f"Skipping directory entry: {name}")
                return None
            
            file_type = 'file'
            is_directory = False
            
            if permissions.startswith('d'):
                file_type = 'directory'
                is_directory = True
            elif permissions.startswith('l'):
                file_type = 'symlink'
            elif permissions.startswith('b'):
                file_type = 'block_device'
            elif permissions.startswith('c'):
                file_type = 'char_device'
            elif permissions.startswith('p'):
                file_type = 'pipe'
            elif permissions.startswith('s'):
                file_type = 'socket'
            
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
                "links": links
            }
            
            if target:
                result["target"] = target.strip()
            
            logger.debug(f"Successfully parsed: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error parsing ls line '{line}': {str(e)}")
            return None

    async def stat_file(self, path: str):
        """Gets detailed information about a file"""
        try:
            logger.info(f"Getting file stats: {path}")
            
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', 
                f'stat "{path}" 2>/dev/null || echo "ERROR: Cannot stat file"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                await self.send_error(f"Cannot stat file: {path}")
                return
                
            output = stdout.decode('utf-8', errors='ignore')
            
            if "ERROR: Cannot stat file" in output:
                await self.send_error(f"Cannot stat file: {path}")
                return
            
            stat_info = self.parse_stat_output(output)
            
            await self.send_response({
                "type": "file_manager",
                "action": "stat",
                "path": path,
                "stat": stat_info
            })
            
        except Exception as e:
            logger.error(f"Error getting file stats {path}: {str(e)}")
            await self.send_error(f"Error getting file stats: {str(e)}")

    def parse_stat_output(self, output: str) -> Dict[str, Any]:
        """Parses the output of the stat command"""
        try:
            lines = output.strip().split('\n')
            stat_info = {}
            
            for line in lines:
                if 'File:' in line:
                    stat_info['file'] = line.split('File:')[1].strip()
                elif 'Size:' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'Size:':
                            stat_info['size'] = int(parts[i+1])
                            break
                elif 'Access:' in line and 'Uid:' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'Access:':
                            stat_info['permissions'] = parts[i+1]
                            break
                elif 'Modify:' in line:
                    stat_info['modified'] = line.split('Modify:')[1].strip()
                elif 'Change:' in line:
                    stat_info['changed'] = line.split('Change:')[1].strip()
                elif 'Birth:' in line:
                    stat_info['created'] = line.split('Birth:')[1].strip()
            
            return stat_info
            
        except Exception as e:
            logger.error(f"Error parsing stat output: {str(e)}")
            return {}

    async def download_file(self, path: str):
        """Downloads a file from the device"""
        try:
            logger.info(f"Downloading file: {path}")
            
            check_command = self.get_shell_command(f'test -f "{path}" && echo "FILE" || echo "NOT_FILE"')
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', check_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if "NOT_FILE" in stdout.decode():
                await self.send_error(f"Path is not a file: {path}")
                return
            
            temp_file = f"/tmp/download_{os.path.basename(path)}_{asyncio.get_event_loop().time()}"
            
            if self.use_su and self.su_available:
                temp_device_path = f"/data/local/tmp/temp_download_{os.path.basename(path)}_{int(asyncio.get_event_loop().time())}"
                
                copy_command = self.get_shell_command(f'cp "{path}" "{temp_device_path}" && chmod 644 "{temp_device_path}"')
                copy_process = await asyncio.create_subprocess_exec(
                    'adb', '-s', self.device_id, 'shell', copy_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                copy_stdout, copy_stderr = await copy_process.communicate()
                
                if copy_process.returncode != 0:
                    await self.send_error(f"Failed to copy file for download: {copy_stderr.decode()}")
                    return
                
                process = await asyncio.create_subprocess_exec(
                    'adb', '-s', self.device_id, 'pull', temp_device_path, temp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                cleanup_command = self.get_shell_command(f'rm "{temp_device_path}"')
                await asyncio.create_subprocess_exec(
                    'adb', '-s', self.device_id, 'shell', cleanup_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    'adb', '-s', self.device_id, 'pull', path, temp_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                await self.send_error(f"Failed to download file: {stderr.decode()}")
                return
            
            try:
                with open(temp_file, 'rb') as f:
                    file_data = f.read()
                
                import base64
                encoded_data = base64.b64encode(file_data).decode('utf-8')
                
                await self.send_response({
                    "type": "file_manager",
                    "action": "download",
                    "path": path,
                    "filename": os.path.basename(path),
                    "size": len(file_data),
                    "data": encoded_data
                })
                
            finally:
                try:
                    os.remove(temp_file)
                except:
                    pass
            
        except Exception as e:
            logger.error(f"Error downloading file {path}: {str(e)}")
            await self.send_error(f"Error downloading file: {str(e)}")

    async def upload_file(self, path: str, data: str):
        """Uploads a file to the device"""
        try:
            logger.info(f"Uploading file: {path}")
            
            import base64
            file_data = base64.b64decode(data)
            
            temp_file = f"/tmp/upload_{os.path.basename(path)}_{asyncio.get_event_loop().time()}"
            
            try:
                with open(temp_file, 'wb') as f:
                    f.write(file_data)
                
                process = await asyncio.create_subprocess_exec(
                    'adb', '-s', self.device_id, 'push', temp_file, path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    await self.send_error(f"Failed to upload file: {stderr.decode()}")
                    return
                
                await self.send_response({
                    "type": "file_manager",
                    "action": "upload",
                    "path": path,
                    "success": True
                })
                
            finally:
                try:
                    os.remove(temp_file)
                except:
                    pass
            
        except Exception as e:
            logger.error(f"Error uploading file {path}: {str(e)}")
            await self.send_error(f"Error uploading file: {str(e)}")

    async def delete_file(self, path: str):
        """Deletes a file or directory"""
        try:
            logger.info(f"Deleting: {path}")
            
            rm_command = self.get_shell_command(f'rm -rf "{path}" && echo "SUCCESS" || echo "FAILED"')
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', rm_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if "FAILED" in stdout.decode() or process.returncode != 0:
                await self.send_error(f"Failed to delete: {path}")
                return
            
            await self.send_response({
                "type": "file_manager",
                "action": "delete",
                "path": path,
                "success": True
            })
            
        except Exception as e:
            logger.error(f"Error deleting {path}: {str(e)}")
            await self.send_error(f"Error deleting: {str(e)}")

    async def create_directory(self, path: str):
        """Creates a directory"""
        try:
            logger.info(f"Creating directory: {path}")
            
            mkdir_command = self.get_shell_command(f'mkdir -p "{path}" && echo "SUCCESS" || echo "FAILED"')
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', mkdir_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if "FAILED" in stdout.decode() or process.returncode != 0:
                await self.send_error(f"Failed to create directory: {path}")
                return
            
            await self.send_response({
                "type": "file_manager",
                "action": "mkdir",
                "path": path,
                "success": True
            })
            
        except Exception as e:
            logger.error(f"Error creating directory {path}: {str(e)}")
            await self.send_error(f"Error creating directory: {str(e)}")

    async def move_file(self, source: str, destination: str):
        """Moves a file or directory"""
        try:
            logger.info(f"Moving {source} to {destination}")
            
            mv_command = self.get_shell_command(f'mv "{source}" "{destination}" && echo "SUCCESS" || echo "FAILED"')
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', mv_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if "FAILED" in stdout.decode() or process.returncode != 0:
                await self.send_error(f"Failed to move {source} to {destination}")
                return
            
            await self.send_response({
                "type": "file_manager",
                "action": "move",
                "source": source,
                "destination": destination,
                "success": True
            })
            
        except Exception as e:
            logger.error(f"Error moving {source} to {destination}: {str(e)}")
            await self.send_error(f"Error moving file: {str(e)}")

    async def copy_file(self, source: str, destination: str):
        """Copies a file or directory"""
        try:
            logger.info(f"Copying {source} to {destination}")
            
            cp_command = self.get_shell_command(f'cp -r "{source}" "{destination}" && echo "SUCCESS" || echo "FAILED"')
            process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell', cp_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if "FAILED" in stdout.decode() or process.returncode != 0:
                await self.send_error(f"Failed to copy {source} to {destination}")
                return
            
            await self.send_response({
                "type": "file_manager",
                "action": "copy",
                "source": source,
                "destination": destination,
                "success": True
            })
            
        except Exception as e:
            logger.error(f"Error copying {source} to {destination}: {str(e)}")
            await self.send_error(f"Error copying file: {str(e)}")

    async def send_response(self, data: Dict[str, Any]):
        """Sends a response to the client"""
        try:
            if self.websocket.client_state.CONNECTED:
                await self.websocket.send_text(json.dumps(data))
            else:
                logger.warning("WebSocket not connected, cannot send response")
        except Exception as e:
            logger.error(f"Error sending response: {str(e)}")

    async def send_error(self, message: str):
        """Sends an error message"""
        await self.send_response({
            "type": "file_manager",
            "action": "error",
            "message": message
        })

    async def stop(self):
        """Stops the file manager"""
        if not self.is_running:
            return

        self.is_running = False
        logger.info(f"File manager stopped for device {self.device_id}") 