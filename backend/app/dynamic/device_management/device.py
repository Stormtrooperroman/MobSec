from typing import Dict, Optional, List
import asyncio
import logging

from app.dynamic.utils.adb_utils import remove_all_port_forwarding
from app.dynamic.utils.adb_utils import execute_adb_shell, execute_adb_command

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
            stdout, _, _ = await execute_adb_shell(
                device_id=self.serial,
                shell_command=f"test -f {PID_FILE} && cat {PID_FILE}",
            )

            if stdout:
                try:
                    pid = int(stdout.strip())
                    ps_stdout, _, _ = await execute_adb_shell(
                        device_id=self.serial,
                        shell_command=f"ps -ef | grep {pid} | grep {SERVER_PROCESS_NAME}",
                    )

                    if ps_stdout:
                        cmd_stdout, _, _ = await execute_adb_shell(
                            device_id=self.serial,
                            shell_command=f"cat /proc/{pid}/cmdline",
                        )

                        if cmd_stdout:
                            args = cmd_stdout.split("\0")
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

            ps_stdout, _, _ = await execute_adb_shell(
                device_id=self.serial,
                shell_command=f"ps -ef | grep {SERVER_PROCESS_NAME} | grep {SERVER_PACKAGE}",
            )

            pids = []
            for line in ps_stdout.splitlines():
                parts = line.split()
                if len(parts) > 1:
                    try:
                        pid = int(parts[1])
                        cmd_stdout, _, _ = await execute_adb_shell(
                            device_id=self.serial,
                            shell_command=f"cat /proc/{pid}/cmdline",
                        )

                        if cmd_stdout:
                            args = cmd_stdout.split("\0")
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
            stdout, stderr, _ = await execute_adb_shell(
                device_id=self.serial,
                shell_command=f"kill {pid}",
            )
            if stderr:
                logger.error("Error killing process %s: %s", pid, stderr)
            return stdout.strip()
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
            await execute_adb_shell(
                device_id=self.serial,
                shell_command=kill_cmd,
            )

            pid_cleanup_cmd = (
                "test -f /data/local/tmp/ws_scrcpy.pid && "
                "cat /data/local/tmp/ws_scrcpy.pid | xargs kill -9"
            )
            await execute_adb_shell(
                device_id=self.serial,
                shell_command=pid_cleanup_cmd,
            )

            await remove_all_port_forwarding(device_id=None)

            await execute_adb_shell(
                device_id=self.serial,
                shell_command="rm -f /data/local/tmp/scrcpy-server.jar /data/local/tmp/ws_scrcpy.pid",
            )

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
                "push",
                server_jar,
                f"{TEMP_PATH}{SERVER_JAR}"
            ]
            stdout, stderr, returncode = await execute_adb_command(
                device_id=self.serial,
                command=push_cmd,
            )
            if returncode != 0:
                logger.error("Failed to push server: %s", stderr)
                return None

            logger.info("Setting up ADB forward...")
            forward_cmd = [
                "forward",
                f"tcp:{self.port}",
                f"tcp:{self.port}"
            ]
            stdout, stderr, returncode = await execute_adb_command(
                device_id=self.serial,
                command=forward_cmd,
            )
            if returncode != 0:
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

            stdout, stderr, _ = await execute_adb_shell(
                device_id=self.serial,
                shell_command=server_cmd,
            )

            if stderr:
                logger.error("Error starting server: %s", stderr)
                return None

            logger.info(
                "Server start stdout: %s", stdout if stdout else "None"
            )

            result = None
            for _ in range(10):
                pids = await self.get_server_pid()
                if pids:
                    pid = pids[0]
                    netstat_stdout, _, _ = await execute_adb_shell(
                        device_id=self.serial,
                        shell_command=f"netstat -ln | grep {self.port}",
                    )

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

                log_stdout, _, _ = await execute_adb_shell(
                    device_id=self.serial,
                    shell_command="cat /data/local/tmp/scrcpy.log",
                )
                if log_stdout:
                    log_content = log_stdout
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
