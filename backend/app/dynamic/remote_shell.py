import asyncio
import json
import logging
import os
import pty
import struct
import termios
import fcntl
from fastapi import WebSocket
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class RemoteShell:
    def __init__(self, websocket: WebSocket, device_id: str):
        self.websocket = websocket
        self.device_id = device_id
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False
        self._read_task = None
        self._error_task = None
        self.rows = 30
        self.cols = 100
        self.master_fd = None
        self.slave_fd = None

    async def start(self):
        """Starts the shell process and begins input/output processing"""
        if self.is_running:
            return False

        try:
            self.master_fd, self.slave_fd = pty.openpty()
            
            term_settings = termios.tcgetattr(self.slave_fd)
            term_settings[3] = term_settings[3] & ~termios.ECHO
            termios.tcsetattr(self.slave_fd, termios.TCSANOW, term_settings)
            
            fcntl.ioctl(self.slave_fd, termios.TIOCSWINSZ, 
                       struct.pack("HHHH", self.rows, self.cols, 0, 0))
            
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['LANG'] = 'en_US.UTF-8'
            env['LC_ALL'] = 'en_US.UTF-8'
            
            logger.info(f"Starting shell for device {self.device_id}")
            
            self.process = await asyncio.create_subprocess_exec(
                'adb', '-s', self.device_id, 'shell',
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                env=env
            )

            if not self.process:
                logger.error("Failed to create shell process")
                return False

            self.is_running = True
            
            os.close(self.slave_fd)
            self.slave_fd = None
            
            self._read_task = asyncio.create_task(self._read_output())
            return True
            
        except Exception as e:
            logger.error(f"Error starting shell: {str(e)}")
            await self.stop()
            return False

    async def _read_output(self):
        """Reads the output of the process from master_fd and sends data to WebSocket"""
        try:
            logger.info("Starting output reader")
            while self.is_running and self.master_fd is not None:
                try:
                    loop = asyncio.get_event_loop()
                    data = await loop.run_in_executor(None, os.read, self.master_fd, 1024)
                    
                    if not data:
                        logger.info("No data from PTY, breaking")
                        break
                    
                    logger.info(f"Read {len(data)} bytes from PTY: {repr(data)}")
                    
                    if self.websocket.client_state.CONNECTED:
                        await self.websocket.send_bytes(data)
                        logger.info(f"Sent {len(data)} bytes to WebSocket")
                    else:
                        logger.warning("WebSocket not connected, cannot send data")
                        
                except (OSError, IOError) as e:
                    if e.errno == 5:
                        logger.info("PTY closed (errno 5)")
                        break
                    logger.error(f"Error reading from PTY: {e}")
                    raise
                    
        except asyncio.CancelledError:
            logger.info("Output reader cancelled")
            pass
        except Exception as e:
            logger.error(f"Error in output reader: {str(e)}")
        finally:
            logger.info("Output reader finished")
            if self.is_running:
                await self.stop()

    async def handle_input(self, data: str):
        """Handles incoming data from WebSocket"""
        try:
            logger.info(f"Received input data: {repr(data)}")
            logger.info(f"Data length: {len(data)}")
            logger.info(f"Data char codes: {[ord(c) for c in data]}")
            
            try:
                message = json.loads(data)
                if message.get('type') == 'shell':
                    shell_data = message.get('data', {})
                    logger.info(f"Shell data: {shell_data}")
                    if shell_data.get('type') == 'start':
                        self.rows = shell_data.get('rows', 30)
                        self.cols = shell_data.get('cols', 100)
                        logger.info(f"Starting shell with size: {self.rows}x{self.cols}")
                        if self.master_fd is not None:
                            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, 
                                      struct.pack("HHHH", self.rows, self.cols, 0, 0))
                    elif shell_data.get('type') == 'resize':
                        self.rows = shell_data.get('rows', 30)
                        self.cols = shell_data.get('cols', 100)
                        logger.info(f"Resizing shell to: {self.rows}x{self.cols}")
                        if self.master_fd is not None:
                            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, 
                                      struct.pack("HHHH", self.rows, self.cols, 0, 0))
                    elif shell_data.get('type') == 'input':
                        input_data = shell_data.get('input', '')
                        logger.info(f"Writing input to PTY: {repr(input_data)}")
                        if self.is_running and self.master_fd is not None:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, os.write, self.master_fd, input_data.encode())
                        else:
                            logger.error(f"Cannot write input: running={self.is_running}, master_fd={self.master_fd}")
                    else:
                        logger.info(f"Unknown shell data type: {shell_data.get('type')}")
                        if self.is_running and self.master_fd is not None:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(None, os.write, self.master_fd, data.encode())
                    return
            except json.JSONDecodeError:
                pass
            
            logger.info(f"Writing raw data to PTY: {repr(data)}")
            logger.info(f"Raw data length: {len(data)}")
            logger.info(f"Raw data char codes: {[ord(c) for c in data]}")
            if self.is_running and self.master_fd is not None:
                try:
                    encoded_data = data.encode()
                    logger.info(f"Encoded data: {repr(encoded_data)}")
                    logger.info(f"Encoded data length: {len(encoded_data)}")
                    loop = asyncio.get_event_loop()
                    bytes_written = await loop.run_in_executor(None, os.write, self.master_fd, encoded_data)
                    logger.info(f"Wrote {bytes_written} bytes to PTY")
                except Exception as e:
                    logger.error(f"Error writing to PTY: {e}")
            else:
                logger.error(f"Cannot write data: running={self.is_running}, master_fd={self.master_fd}")
                
        except Exception as e:
            logger.error(f"Error handling input: {str(e)}")
            await self.stop()

    async def stop(self):
        """Stops the shell process and frees resources"""
        if not self.is_running:
            return

        self.is_running = False

        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None
            
        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except:
                pass
            self.slave_fd = None

        if self.process:
            try:
                self.process.kill()
                await self.process.wait()
            except:
                pass

        self.process = None 