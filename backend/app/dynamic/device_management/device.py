from typing import Dict, Optional, List
import asyncio
import logging

from app.dynamic.utils.adb_utils import remove_all_port_forwarding


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


TEMP_PATH = "/data/local/tmp/"
SERVER_JAR = "scrcpy-server.jar"
SERVER_PACKAGE = "com.genymobile.scrcpy.Server"
SERVER_PROCESS_NAME = "app_process"
SERVER_VERSION = "1.19-ws6"
SERVER_TYPE = "web"
PID_FILE = f"{TEMP_PATH}ws_scrcpy.pid"


class Device:
    def __init__(self, serial: str, state: str):
        self.serial = serial
        self.state = state
        self.tag = f"[{serial}]"
        self.connected = state == "device"
        self.properties: Optional[Dict[str, str]] = None
        self.port = 8886
        self.device_type = "unknown"
        self.display_name = serial
        self.proxy_configured = False

    async def get_server_pid(self) -> List[int]:
        """Get PID of running scrcpy server process"""
        try:
            cat_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                f"test -f {PID_FILE} && cat {PID_FILE}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await cat_process.communicate()

            if stdout:
                try:
                    pid = int(stdout.decode().strip())
                    ps_process = await asyncio.create_subprocess_exec(
                        "adb",
                        "-s",
                        self.serial,
                        "shell",
                        f"ps -ef | grep {pid} | grep {SERVER_PROCESS_NAME}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    ps_stdout, _ = await ps_process.communicate()

                    if ps_stdout:
                        cmd_process = await asyncio.create_subprocess_exec(
                            "adb",
                            "-s",
                            self.serial,
                            "shell",
                            f"cat /proc/{pid}/cmdline",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        cmd_stdout, _ = await cmd_process.communicate()

                        if cmd_stdout:
                            args = cmd_stdout.decode().split("\0")
                            if SERVER_PACKAGE in args:
                                pkg_index = args.index(SERVER_PACKAGE)
                                if len(args) > pkg_index + 1:
                                    version = args[pkg_index + 1]
                                    if version == SERVER_VERSION:
                                        return [pid]

                                    logger.info(
                                        "Found old server version running (PID: %s, Version: %s)",
                                        pid,
                                        version,
                                    )
                                    await self.kill_process(pid)
                except ValueError:
                    logger.error("Invalid PID in PID file")

            ps_process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                f"ps -ef | grep {SERVER_PROCESS_NAME} | grep {SERVER_PACKAGE}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            ps_stdout, _ = await ps_process.communicate()

            pids = []
            for line in ps_stdout.decode().splitlines():
                parts = line.split()
                if len(parts) > 1:
                    try:
                        pid = int(parts[1])
                        cmd_process = await asyncio.create_subprocess_exec(
                            "adb",
                            "-s",
                            self.serial,
                            "shell",
                            f"cat /proc/{pid}/cmdline",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        cmd_stdout, _ = await cmd_process.communicate()

                        if cmd_stdout:
                            args = cmd_stdout.decode().split("\0")
                            if SERVER_PACKAGE in args:
                                pkg_index = args.index(SERVER_PACKAGE)
                                if len(args) > pkg_index + 1:
                                    version = args[pkg_index + 1]
                                    if version == SERVER_VERSION:
                                        pids.append(pid)
                                    else:
                                        logger.info(
                                            "Found old server version running "
                                            "(PID: %s, Version: %s)",
                                            pid,
                                            version,
                                        )
                                        await self.kill_process(pid)
                    except ValueError:
                        continue

            return pids

        except Exception as e:
            logger.error("Error getting server PID: %s", e)
            return []

    async def kill_process(self, pid: int) -> Optional[str]:
        """Kill a process on the device"""
        try:
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                f"kill {pid}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if stderr:
                logger.error("Error killing process %s: %s", pid, stderr.decode())
            return stdout.decode().strip()
        except Exception as e:
            logger.error("Error killing process: %s", e)
            return None

    async def kill_server(self):
        """Kill scrcpy server and clean up resources"""
        try:
            logger.info("Killing all scrcpy processes for device: %s", self.serial)

            kill_cmd = (
                "ps -ef | grep 'app_process.*scrcpy' | grep -v grep | "
                "awk '{print $2}' | xargs -r kill -9"
            )
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                kill_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            pid_cleanup_cmd = (
                "test -f /data/local/tmp/ws_scrcpy.pid && "
                "cat /data/local/tmp/ws_scrcpy.pid | xargs kill -9"
            )
            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                pid_cleanup_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            _, _, _ = await remove_all_port_forwarding(device_id=None)

            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                "rm -f /data/local/tmp/scrcpy-server.jar /data/local/tmp/ws_scrcpy.pid",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            await asyncio.sleep(2)
            logger.info(
                "Killed all scrcpy processes and cleaned up for device: %s",
                self.serial,
            )

        except Exception as e:
            logger.error("Error killing scrcpy processes: %s", e)

    async def start_server(self) -> Optional[Dict]:
        """Start scrcpy server on the device"""
        try:
            logger.info("Starting scrcpy server for device: %s", self.serial)

            await self.kill_server()

            logger.info("Pushing server to device...")
            server_jar = "/app/scrcpy-server.jar"
            push_cmd = [
                "adb",
                "-s",
                self.serial,
                "push",
                server_jar,
                f"{TEMP_PATH}{SERVER_JAR}",
            ]
            process = await asyncio.create_subprocess_exec(
                *push_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                logger.error("Failed to push server: %s", stderr.decode())
                return None

            logger.info("Setting up ADB forward...")
            forward_cmd = [
                "adb",
                "-s",
                self.serial,
                "forward",
                f"tcp:{self.port}",
                f"tcp:{self.port}",
            ]
            process = await asyncio.create_subprocess_exec(
                *forward_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            if process.returncode != 0:
                logger.error("Failed to set up ADB forward")
                return None

            args_string = (
                f"/ {SERVER_PACKAGE} {SERVER_VERSION} {SERVER_TYPE} "
                f"debug {self.port} true"
            )
            server_cmd = (
                f"CLASSPATH={TEMP_PATH}{SERVER_JAR} "
                f"nohup {SERVER_PROCESS_NAME} {args_string} > /data/local/tmp/scrcpy.log 2>&1 & "
                f"echo $! > {PID_FILE}"
            )

            logger.info("Starting server with command: %s", server_cmd)

            process = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                self.serial,
                "shell",
                server_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if stderr:
                logger.error("Error starting server: %s", stderr.decode())
                return None

            logger.info(
                "Server start stdout: %s", stdout.decode() if stdout else "None"
            )

            result = None
            for _ in range(10):
                pids = await self.get_server_pid()
                if pids:
                    pid = pids[0]
                    netstat_process = await asyncio.create_subprocess_exec(
                        "adb",
                        "-s",
                        self.serial,
                        "shell",
                        f"netstat -ln | grep {self.port}",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    netstat_stdout, _ = await netstat_process.communicate()

                    if netstat_stdout:
                        logger.info(
                            "Scrcpy server started successfully with PID: %s",
                            pid,
                        )
                        result = {
                            "pid": pid,
                            "port": self.port,
                            "device_id": self.serial,
                        }
                        break

                    logger.info("Server process running but not listening yet")

                log_process = await asyncio.create_subprocess_exec(
                    "adb",
                    "-s",
                    self.serial,
                    "shell",
                    "cat /data/local/tmp/scrcpy.log",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                log_stdout, _ = await log_process.communicate()
                if log_stdout:
                    log_content = log_stdout.decode()
                    if "ERROR" in log_content or "Exception" in log_content:
                        logger.error("Server error in log: %s", log_content)
                        result = None
                        break

                await asyncio.sleep(1)

            if result:
                return result

            logger.error("Failed to verify server is running")
            return None

        except Exception as e:
            logger.error("Error starting scrcpy server: %s", e)
            return None
