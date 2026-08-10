import asyncio
import json
import logging
import os
import time
import socket
import hashlib
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime
from io import BytesIO
from fastapi import WebSocket

from mitmproxy import options, flow, io as mitmproxy_io, certs
from mitmproxy import flowfilter
from mitmproxy.http import HTTPFlow
from mitmproxy.tcp import TCPFlow
from mitmproxy.udp import UDPFlow
from mitmproxy.dns import DNSFlow
from mitmproxy.utils.emoji import emoji
from mitmproxy.utils.strutils import always_str

from web_master import WebMaster
from mobsec_modules_library.dynamic.adb_utils import (
    check_su_availability,
    execute_adb_command,
    execute_adb_shell,
)

logger = logging.getLogger(__name__)


def cert_to_json(cert_list) -> dict | None:
    """Convert certificate to JSON format"""
    if not cert_list:
        return None
    cert = cert_list[0]
    return {
        "keyinfo": cert.keyinfo,
        "sha256": cert.fingerprint().hex(),
        "notbefore": int(cert.notbefore.timestamp()),
        "notafter": int(cert.notafter.timestamp()),
        "serial": str(cert.serial),
        "subject": cert.subject,
        "issuer": cert.issuer,
        "altnames": [str(x.value) for x in cert.altnames],
    }


__all__ = [
    "cert_to_json",
    "flow_to_json",
    "MitmproxyManager",
    "get_mitmproxy_manager",
    "cleanup_mitmproxy_manager",
]


def _extract_content(message) -> tuple[str | None, str | None]:
    try:
        raw_data = message.get_content(strict=False)
    except Exception as e:
        logger.warning("Error getting content: %s", e)
        return None, None

    if raw_data is None:
        return None, None

    try:
        return raw_data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return base64.b64encode(raw_data).decode("ascii"), "base64"


def flow_to_json(flow_obj: flow.Flow) -> dict:
    """
    Convert flow to JSON format
    """
    f = {
        "id": flow_obj.id,
        "intercepted": flow_obj.intercepted,
        "is_replay": flow_obj.is_replay,
        "type": flow_obj.type,
        "modified": flow_obj.modified(),
        "marked": emoji.get(flow_obj.marked, "🔴") if flow_obj.marked else "",
        "comment": flow_obj.comment,
        "timestamp_created": flow_obj.timestamp_created,
    }

    if flow_obj.client_conn:
        f["client_conn"] = {
            "id": flow_obj.client_conn.id,
            "peername": flow_obj.client_conn.peername,
            "sockname": flow_obj.client_conn.sockname,
            "tls_established": flow_obj.client_conn.tls_established,
            "cert": cert_to_json(flow_obj.client_conn.certificate_list),
            "sni": flow_obj.client_conn.sni,
            "cipher": flow_obj.client_conn.cipher,
            "alpn": always_str(flow_obj.client_conn.alpn, "ascii", "backslashreplace"),
            "tls_version": flow_obj.client_conn.tls_version,
            "timestamp_start": flow_obj.client_conn.timestamp_start,
            "timestamp_tls_setup": flow_obj.client_conn.timestamp_tls_setup,
            "timestamp_end": flow_obj.client_conn.timestamp_end,
        }

    if flow_obj.server_conn:
        f["server_conn"] = {
            "id": flow_obj.server_conn.id,
            "peername": flow_obj.server_conn.peername,
            "sockname": flow_obj.server_conn.sockname,
            "address": flow_obj.server_conn.address,
            "tls_established": flow_obj.server_conn.tls_established,
            "cert": cert_to_json(flow_obj.server_conn.certificate_list),
            "sni": flow_obj.server_conn.sni,
            "cipher": flow_obj.server_conn.cipher,
            "alpn": always_str(flow_obj.server_conn.alpn, "ascii", "backslashreplace"),
            "tls_version": flow_obj.server_conn.tls_version,
            "timestamp_start": flow_obj.server_conn.timestamp_start,
            "timestamp_tcp_setup": flow_obj.server_conn.timestamp_tcp_setup,
            "timestamp_tls_setup": flow_obj.server_conn.timestamp_tls_setup,
            "timestamp_end": flow_obj.server_conn.timestamp_end,
        }

    if flow_obj.error:
        f["error"] = flow_obj.error.get_state()

    if isinstance(flow_obj, HTTPFlow):
        content_length: int | None
        content_hash: str | None

        if flow_obj.request.raw_content is not None:
            content_length = len(flow_obj.request.raw_content)
            content_hash = hashlib.sha256(flow_obj.request.raw_content).hexdigest()
        else:
            content_length = None
            content_hash = None

        request_content, request_content_encoding = _extract_content(flow_obj.request)

        f["request"] = {
            "method": flow_obj.request.method,
            "scheme": flow_obj.request.scheme,
            "host": flow_obj.request.host,
            "port": flow_obj.request.port,
            "path": flow_obj.request.path,
            "http_version": flow_obj.request.http_version,
            "headers": tuple(flow_obj.request.headers.items(True)),
            "contentLength": content_length,
            "contentHash": content_hash,
            "content": request_content,
            "content_encoding": request_content_encoding,
            "timestamp_start": flow_obj.request.timestamp_start,
            "timestamp_end": flow_obj.request.timestamp_end,
            "pretty_host": flow_obj.request.pretty_host,
        }
        if flow_obj.response:
            if flow_obj.response.raw_content is not None:
                content_length = len(flow_obj.response.raw_content)
                content_hash = hashlib.sha256(flow_obj.response.raw_content).hexdigest()
            else:
                content_length = None
                content_hash = None

            response_content, response_content_encoding = _extract_content(
                flow_obj.response
            )

            f["response"] = {
                "http_version": flow_obj.response.http_version,
                "status_code": flow_obj.response.status_code,
                "reason": flow_obj.response.reason,
                "headers": tuple(flow_obj.response.headers.items(True)),
                "contentLength": content_length,
                "contentHash": content_hash,
                "content": response_content,
                "content_encoding": response_content_encoding,
                "timestamp_start": flow_obj.response.timestamp_start,
                "timestamp_end": flow_obj.response.timestamp_end,
            }
            if flow_obj.response.data.trailers:
                f["response"]["trailers"] = tuple(
                    flow_obj.response.data.trailers.items(True)
                )

        if flow_obj.websocket:
            f["websocket"] = {
                "messages_meta": {
                    "contentLength": sum(
                        len(x.content) for x in flow_obj.websocket.messages
                    ),
                    "count": len(flow_obj.websocket.messages),
                    "timestamp_last": (
                        flow_obj.websocket.messages[-1].timestamp
                        if flow_obj.websocket.messages
                        else None
                    ),
                },
                "closed_by_client": flow_obj.websocket.closed_by_client,
                "close_code": flow_obj.websocket.close_code,
                "close_reason": flow_obj.websocket.close_reason,
                "timestamp_end": flow_obj.websocket.timestamp_end,
            }
    elif isinstance(flow_obj, (TCPFlow, UDPFlow)):
        f["messages_meta"] = {
            "contentLength": sum(len(x.content) for x in flow_obj.messages),
            "count": len(flow_obj.messages),
            "timestamp_last": (
                flow_obj.messages[-1].timestamp if flow_obj.messages else None
            ),
        }
    elif isinstance(flow_obj, DNSFlow):
        f["request"] = flow_obj.request.to_json()
        if flow_obj.response:
            f["response"] = flow_obj.response.to_json()

    return f


class MitmproxyManager:
    """Mitmproxy Manager"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.proxy_configured = False

        self.is_running = False

        # Proxy settings
        self.proxy_port = 8082
        self.proxy_host = "0.0.0.0"
        self.device_ip = None
        self.backend_ip = None

        # Mitmproxy components
        self.master_instance: Optional[WebMaster] = None
        self.proxy_task = None

        # Device state
        self.su_available = False
        self.cert_installed = False

        # WebSocket connections
        self._active_websockets = set()

        # Paths and directories
        self.certs_dir = "/tmp/mitmproxy/certs"
        self.data_dir = "/tmp/mitmproxy/data"

        # Create necessary directories
        os.makedirs(self.certs_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)

    async def _initialize_master(self):
        """Initialize mitmproxy master"""
        try:
            # If master instance already exists, stop it first
            if self.master_instance is not None:
                try:
                    if hasattr(self.master_instance, "shutdown"):
                        self.master_instance.shutdown()
                except Exception as e:
                    logger.warning("Error shutting down existing master: %s", e)
                logger.info("Setting master_instance to None in _initialize_master()")
                self.master_instance = None

            # Check port availability before initialization
            if not await self._check_port_available(self.proxy_port):
                logger.warning(
                    "Port %s is not available during initialization", self.proxy_port
                )
                # Try to safely release the port
                await self._safe_release_port()
                if not await self._check_port_available(self.proxy_port):

                    logger.info("Waiting for port to become available...")
                    await asyncio.sleep(3)
                    if not await self._check_port_available(self.proxy_port):
                        # Last attempt - find any available port
                        logger.info("Trying to find any available port...")
                        for test_port in range(8082, 8100):
                            if await self._check_port_available(test_port):
                                logger.info("Found available port %s", test_port)
                                self.proxy_port = test_port
                                break
                        else:
                            raise RuntimeError(
                                "Could not find any available port in range 8082-8100"
                            )

            opts = options.Options(
                listen_port=self.proxy_port,
                listen_host=self.proxy_host,
                confdir=self.data_dir,
            )
            self.master_instance = WebMaster(opts, with_termlog=False)

            # Add callbacks
            self.master_instance.add_flow_callback(self._handle_flow_event)
            self.master_instance.add_event_callback(self._handle_log_event)
            self.master_instance.add_option_callback(self._handle_option_event)

            logger.info("Mitmproxy master initialized on port %s", self.proxy_port)
        except Exception as e:
            logger.error("Error initializing mitmproxy master: %s", e)
            raise

    def _handle_flow_event(self, event_type: str, flow_obj):
        """Handle flow events"""
        try:
            # Log the event
            flow_id = flow_obj.id if flow_obj else "None"
            logger.debug("Flow event: %s - %s", event_type, flow_id)

            if hasattr(self, "_active_websockets") and self._active_websockets:
                # Determine the correct action name based on event_type
                action_name = ""
                if event_type == "flows/add":
                    action_name = "flow_add"
                elif event_type == "flows/update":
                    action_name = "flow_update"
                elif event_type == "flows/remove":
                    action_name = "flow_remove"
                elif event_type == "flows/refresh":
                    action_name = "flows_refresh"  # Or handle as a full flows update

                if action_name:  # Only send if a recognized action
                    event_data = {
                        "type": "mitmproxy",  # Keep type as mitmproxy
                        "action": action_name,
                        "flow": flow_to_json(flow_obj) if flow_obj else None,
                        "device_id": self.device_id,
                    }

                    # Send to all active WebSocket connections
                    for websocket in self._active_websockets:
                        try:
                            asyncio.create_task(
                                websocket.send_text(json.dumps(event_data))
                            )
                        except Exception as ws_error:
                            logger.warning(
                                "Failed to send flow event to WebSocket: %s", ws_error
                            )

        except Exception as event_error:
            logger.error("Error in flow event handler: %s", event_error)

    def _handle_log_event(self, event_type: str, log_entry):
        """Handle log events"""
        try:
            # Just log the event
            msg = getattr(log_entry, "msg", str(log_entry))
            logger.debug("Log event: %s - %s", event_type, msg)
        except Exception as log_error:
            logger.error("Error in log event handler: %s", log_error)

    def _handle_option_event(self, event_type: str, options_dict):
        """Handle option change events"""
        try:
            # Just log the event
            logger.debug("Option event: %s - %s", event_type, options_dict)
        except Exception as e:
            logger.error("Error in option event handler: %s", e)

    def add_websocket(self, websocket):
        """Add WebSocket connection for real-time updates"""
        self._active_websockets.add(websocket)
        logger.info(
            "Added WebSocket for device %s, total: %d",
            self.device_id,
            len(self._active_websockets),
        )

    def remove_websocket(self, websocket):
        """Remove WebSocket connection"""
        self._active_websockets.discard(websocket)
        logger.info(
            "Removed WebSocket for device %s, total: %d",
            self.device_id,
            len(self._active_websockets),
        )

    async def start(self) -> bool:
        """Start mitmproxy manager"""
        try:
            self.is_running = True
            logger.info("Starting Mitmproxy manager for device %s", self.device_id)

            # Only initialize master if it doesn't exist
            if self.master_instance is None:
                await self._initialize_master()
            else:
                logger.info("Reusing existing master instance (preserving flows)")

            # Check if proxy is already running
            if self.proxy_task and not self.proxy_task.done():
                return True
            proxy_started = await self.start_proxy()
            if not proxy_started:
                logger.error("Failed to start proxy")
                return False

            # Initialize backend_ip if it's not set
            if not self.backend_ip or self.backend_ip == "172.19.0.1":
                # Create a task for asynchronous IP retrieval
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If event loop is running, create a task
                        asyncio.create_task(self._initialize_backend_ip())
                    else:
                        # If event loop is not running, start a new one
                        asyncio.run(self._initialize_backend_ip())
                except Exception as init_error:
                    logger.warning("Could not initialize backend IP: %s", init_error)

            return True

        except Exception as e:
            logger.error("Error starting Mitmproxy manager: %s", str(e))
            self.is_running = False
            return False

    async def stop(self, cleanup=False) -> bool:
        """Stop mitmproxy manager

        Args:
            cleanup: If True, clears master_instance and all flows. If False, preserves flows for reuse.
        """
        try:
            logger.info("Stopping Mitmproxy manager for device %s", self.device_id)

            # Use safe shutdown method that follows recommendations from GitHub issue #7237
            await self.stop_proxy_threadsafe(cleanup=cleanup)
            self.is_running = False

            # Only reset master instance if cleanup is requested
            if cleanup:
                logger.info("Clearing master instance")
                self.master_instance = None
            else:
                logger.info("Preserving master instance for future use")

            # Safely release the port
            await self._safe_release_port()

            logger.info("Mitmproxy manager stopped successfully")
            return True

        except Exception as e:
            logger.error("Error stopping Mitmproxy manager: %s", str(e))
            return False

    async def start_proxy(self) -> bool:
        """Start the proxy server"""
        try:
            # Only create master if it doesn't exist
            if self.master_instance is None:
                logger.info("No master instance, initializing...")
                await self._initialize_master()
            else:
                logger.info("Reusing existing master instance (preserving flows)")

            if self.proxy_task and not self.proxy_task.done():
                logger.info("Proxy is already running")
                return True

            logger.info("Starting proxy on %s:%s", self.proxy_host, self.proxy_port)

            # Create an asynchronous task to start the proxy
            self.proxy_task = asyncio.create_task(self._run_proxy())

            # Wait a bit for the proxy to start
            await asyncio.sleep(2)

            # Check if proxy is listening
            if self._check_port_listening(self.proxy_port):
                logger.info("Proxy started successfully on port %s", self.proxy_port)
                return True

            logger.error("Proxy failed to start")
            return False

        except Exception as e:
            logger.error("Error starting proxy: %s", str(e))
            return False

    async def stop_proxy(self) -> bool:
        """Stop the proxy server"""
        try:
            logger.info(
                "stop_proxy() called - master_instance: %s",
                self.master_instance is not None,
            )
            if self.master_instance is None:
                logger.info("Master instance is already None, nothing to stop")
                return True

            # First disable the server, as recommended in GitHub issue #7237
            try:
                logger.info(
                    "stop_proxy() - master_instance: %s",
                    self.master_instance is not None,
                )
                if self.master_instance is not None:
                    logger.info(
                        "stop_proxy() - master_instance type: %s",
                        type(self.master_instance),
                    )
                    logger.info(
                        "stop_proxy() - master_instance has options: %s",
                        hasattr(self.master_instance, "options"),
                    )

                logger.info("Disabling server before shutdown")
                # Update options to disable the server
                self.master_instance.options.update(server=False)
                logger.info("Server disabled")
            except Exception as server_error:
                logger.warning("Could not disable server: %s", server_error)

            # Stop the master instance
            try:
                logger.info("Shutting down master instance")
                self.master_instance.shutdown()
                logger.info("Master instance shutdown")
            except Exception as shutdown_error:
                logger.warning("Could not shutdown master instance: %s", shutdown_error)

            # Force close all sockets
            try:
                if hasattr(self.master_instance, "addons"):
                    # Get the list of addons safely
                    addons_list = list(self.master_instance.addons.chain)
                    for addon in addons_list:
                        if hasattr(addon, "shutdown"):
                            try:
                                addon.shutdown()
                            except Exception as addon_error:
                                logger.warning(
                                    "Error shutting down addon %s: %s",
                                    type(addon).__name__,
                                    addon_error,
                                )
            except Exception as e:
                logger.warning("Error shutting down addons: %s", e)

            # Reset master instance for creating a new one on next startup
            logger.info("Setting master_instance to None in stop_proxy()")
            self.master_instance = None

            if self.proxy_task:
                self.proxy_task.cancel()
                try:
                    await self.proxy_task
                except asyncio.CancelledError:
                    logger.info("Proxy task cancelled")
                self.proxy_task = None

            # Safely release the port
            await self._safe_release_port()

            logger.info("Proxy stopped")
            return True

        except Exception as e:
            logger.error("Error stopping proxy: %s", str(e))
            return False

    async def stop_proxy_threadsafe(self, cleanup=False) -> bool:
        """Stop the proxy server from another thread safely

        Args:
            cleanup: If True, clears master_instance and all flows. If False, preserves flows for reuse.
        """
        try:
            if self.master_instance is None:
                return True

            # Save reference to master_instance at function creation time
            master_instance_ref = self.master_instance

            # Use call_soon_threadsafe for safe call from another thread
            def stop_server():
                try:
                    logger.info(
                        "stop_server() called - master_instance_ref: %s",
                        master_instance_ref is not None,
                    )
                    if master_instance_ref is not None:
                        logger.info(
                            "master_instance_ref type: %s", type(master_instance_ref)
                        )
                        logger.info(
                            "master_instance_ref has options: %s",
                            hasattr(master_instance_ref, "options"),
                        )
                        if hasattr(master_instance_ref, "options"):
                            logger.info("Disabling server before shutdown (threadsafe)")
                            master_instance_ref.options.update(server=False)
                            logger.info("Server disabled (threadsafe)")
                        else:
                            logger.warning(
                                "Master instance exists but has no options attribute"
                            )
                    else:
                        logger.warning("Master instance reference is None")
                except Exception as e:
                    logger.warning("Could not disable server (threadsafe): %s", e)

            event_loop = master_instance_ref.event_loop if master_instance_ref else None
            logger.info(
                "stop_server() called: %s %s",
                hasattr(master_instance_ref, "event_loop"),
                event_loop,
            )
            # Call function in master instance event loop
            if (
                hasattr(master_instance_ref, "event_loop")
                and master_instance_ref.event_loop
            ):
                try:
                    master_instance_ref.event_loop.call_soon_threadsafe(stop_server)
                    logger.info("Server stop scheduled in event loop")
                    # Give time for stop_server() to execute in event loop
                    time.sleep(1.0)
                    logger.info("Server stop should be completed in event loop")
                except Exception as loop_error:
                    logger.warning(
                        "Could not schedule server stop in event loop: %s", loop_error
                    )
                    # Fallback to regular call
                    stop_server()
            else:
                # Fallback to regular call
                logger.info("No event loop available, using direct call")
                stop_server()

            # Stop the master instance
            try:
                logger.info("Shutting down master instance (threadsafe)")
                master_instance_ref.shutdown()
                logger.info("Master instance shutdown (threadsafe)")
            except Exception as shutdown_error:
                logger.warning(
                    "Could not shutdown master instance (threadsafe): %s",
                    shutdown_error,
                )

            # Force close all sockets and addons
            try:
                if hasattr(master_instance_ref, "addons"):
                    # Get the list of addons safely
                    addons_list = list(master_instance_ref.addons.chain)
                    for addon in addons_list:
                        if hasattr(addon, "shutdown"):
                            try:
                                addon.shutdown()
                            except Exception as addon_error:
                                logger.warning(
                                    "Error shutting down addon %s: %s",
                                    type(addon).__name__,
                                    addon_error,
                                )
            except Exception as e:
                logger.warning("Error shutting down addons: %s", e)

            # Reset master instance only if cleanup is requested
            if cleanup:
                self.master_instance = None

            if self.proxy_task:
                self.proxy_task.cancel()
                try:
                    await self.proxy_task
                except asyncio.CancelledError:
                    logger.info("Proxy task cancelled")
                self.proxy_task = None

            # Force release port with multiple attempts
            logger.info("Starting aggressive port release...")
            for attempt in range(3):
                logger.info("Port release attempt %s/3", attempt + 1)
                await self._safe_release_port()
                if await self._check_port_available(self.proxy_port):
                    logger.info(
                        "Port %s successfully released on attempt %s",
                        self.proxy_port,
                        attempt + 1,
                    )
                    break
                time.sleep(2)

            logger.info("Proxy stopped (threadsafe)")
            return True

        except Exception as e:
            logger.error("Error stopping proxy (threadsafe): %s", str(e))
            return False

    async def _run_proxy(self):
        """Run proxy asynchronously"""
        try:
            if self.master_instance:
                # Start master in current event loop
                await self.master_instance.run()
        except Exception as e:
            logger.error("Error in proxy task: %s", str(e))

    # Flow management methods
    def get_flows(self) -> List[flow.Flow]:
        """Get all flows"""
        if not self.master_instance:
            return []
        return list(self.master_instance.view)

    def get_flow_by_id(self, flow_id: str) -> Optional[flow.Flow]:
        """Get flow by ID"""
        if not self.master_instance:
            return None
        return self.master_instance.view.get_by_id(flow_id)

    def filter_flows(self, flows: List[flow.Flow], filter_expr: str) -> List[flow.Flow]:
        """Filter flows by expression"""
        try:
            if not filter_expr:
                return flows

            filter_func = flowfilter.parse(filter_expr)
            return [f for f in flows if filter_func(f)]
        except Exception as e:
            logger.error("Error filtering flows: %s", e)
            return flows

    def clear_flows(self) -> bool:
        """Clear all flows"""
        try:
            if self.master_instance and self.master_instance.view:
                self.master_instance.view.clear()
                return True
            return False
        except Exception as e:
            logger.error("Error clearing flows: %s", e)
            return False

    def delete_flow(self, flow_id: str) -> bool:
        """Delete a flow"""
        try:
            if not self.master_instance:
                return False

            flow_obj = self.get_flow_by_id(flow_id)
            if flow_obj:
                self.master_instance.view.remove([flow_obj])
                return True
            return False
        except Exception as e:
            logger.error("Error deleting flow: %s", e)
            return False

    def replay_flow(self, flow_obj: flow.Flow) -> bool:
        """Replay a flow"""
        try:
            if self.master_instance and hasattr(self.master_instance, "commands"):
                self.master_instance.commands.call("replay.client", [flow_obj])
                return True
            return False
        except Exception as e:
            logger.error("Error replaying flow: %s", e)
            return False

    async def export_traffic(self, export_format: str = "json") -> Any:
        """Export captured traffic in specified format"""
        try:
            flows = self.get_flows()

            if export_format == "json":
                flows_data = []
                for flow_obj in flows:
                    flows_data.append(flow_to_json(flow_obj))
                return flows_data

            raise ValueError(f"Unsupported export format: {export_format}")

        except Exception as e:
            logger.error("Error exporting traffic: %s", e)
            raise

    async def handle_message(self, websocket: WebSocket, data: str):
        """Handle WebSocket message"""
        try:
            message = json.loads(data)

            if "device_id" in message and message["device_id"] != self.device_id:
                expected = self.device_id
                got = message["device_id"]
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "error",
                        "message": f"Device ID mismatch: expected {expected}, got {got}",
                    },
                )
                return

            if message.get("type") == "mitmproxy":
                action = message.get("action")

                if action == "get_flows":
                    flows = self.get_flows()
                    flows_data = [flow_to_json(flow) for flow in flows]
                    await self.send_response(
                        websocket,
                        {"type": "mitmproxy", "action": "flows", "data": flows_data},
                    )

                elif action == "clear_flows":
                    success = self.clear_flows()
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "clear_flows",
                            "success": success,
                        },
                    )

                elif action == "get_state":
                    self.su_available = await check_su_availability(self.device_id)

                    if not self.backend_ip:
                        self.backend_ip = await self._get_backend_ip()

                    state = await self.get_state()
                    state["su_available"] = self.su_available
                    await self.send_response(
                        websocket,
                        {"type": "mitmproxy", "action": "state", "data": state},
                    )

                elif action == "get_port":
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "port",
                            "port": self.proxy_port,
                            "available": await self._check_port_available(
                                self.proxy_port
                            ),
                            "listening": self._check_port_listening(self.proxy_port),
                        },
                    )

                elif action == "set_port":
                    new_port = message.get("port", self.proxy_port)
                    success = await self.set_proxy_port(new_port)
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "set_port",
                            "success": success,
                            "port": self.proxy_port,
                        },
                    )

                elif action == "force_cleanup":
                    await self._safe_release_port()
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "force_cleanup",
                            "success": True,
                            "message": "Safe cleanup completed",
                        },
                    )

                elif action == "start_proxy":
                    success = await self.start_proxy()
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "proxy_start_result",
                            "success": success,
                        },
                    )

                elif action == "stop_proxy":
                    success = await self.stop_proxy()
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "proxy_stop_result",
                            "success": success,
                        },
                    )

                elif action == "configure_proxy":
                    success = await self.configure_device_proxy(websocket)
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "proxy_configured",
                            "success": success,
                        },
                    )

                elif action == "disable_proxy":
                    success = await self.disable_device_proxy(websocket)
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "proxy_disabled",
                            "success": success,
                        },
                    )

                elif action == "generate_certificate":
                    cert_path = await self.generate_certificate()
                    success = cert_path is not None and os.path.exists(cert_path)
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "certificate_generated",
                            "success": success,
                        },
                    )

                elif action == "install_certificate":
                    success = await self.install_certificate(websocket)
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "certificate_installed",
                            "success": success,
                        },
                    )

                elif action == "download_certificate":
                    cert_path = await self.generate_certificate()
                    if cert_path and os.path.exists(cert_path):
                        with open(cert_path, "rb") as cert_file:
                            cert_content = base64.b64encode(cert_file.read()).decode(
                                "ascii"
                            )
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "certificate_download",
                                "success": True,
                                "content": cert_content,
                                "filename": f"mitmproxy-cert-{self.device_id.replace(':', '_')}.pem",
                                "mime_type": "application/x-pem-file",
                                "message": "Certificate downloaded",
                            },
                        )
                    else:
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "certificate_download",
                                "success": False,
                                "message": "Certificate could not be generated",
                            },
                        )

                elif action == "export_flows":
                    export_format = message.get("format", "json")
                    try:
                        exported = await self.export_traffic(export_format)
                        if isinstance(exported, bytes):
                            payload = exported
                            mime_type = "application/octet-stream"
                        else:
                            payload = json.dumps(exported, indent=2).encode("utf-8")
                            mime_type = "application/json"
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "flows_export",
                                "success": True,
                                "content": base64.b64encode(payload).decode("ascii"),
                                "filename": f"flows_{int(time.time())}.{export_format}",
                                "mime_type": mime_type,
                                "message": f"Traffic exported in {export_format.upper()} format",
                            },
                        )
                    except ValueError as export_error:
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "flows_export",
                                "success": False,
                                "message": str(export_error),
                            },
                        )

                elif action == "reboot_device":
                    # Simple device reboot implementation
                    try:

                        _, stderr, returncode = await execute_adb_command(
                            device_id=self.device_id, command=["reboot"]
                        )

                        success = returncode == 0
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "device_rebooted",
                                "success": success,
                                "message": (
                                    "Device rebooted"
                                    if success
                                    else f"Reboot failed: {stderr}"
                                ),
                            },
                        )
                    except Exception as e:
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "device_rebooted",
                                "success": False,
                                "message": f"Reboot error: {str(e)}",
                            },
                        )

                elif action == "resume_flow":
                    flow_id = message.get("flow_id")
                    if flow_id:
                        flow_obj = self.get_flow_by_id(flow_id)
                        if flow_obj:
                            success = self.replay_flow(flow_obj)
                            await self.send_response(
                                websocket,
                                {
                                    "type": "mitmproxy",
                                    "action": "flow_resumed",
                                    "success": success,
                                    "flow_id": flow_id,
                                },
                            )
                        else:
                            await self.send_response(
                                websocket,
                                {
                                    "type": "mitmproxy",
                                    "action": "flow_resumed",
                                    "success": False,
                                    "flow_id": flow_id,
                                    "message": "Flow not found",
                                },
                            )
                    else:
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "error",
                                "message": "flow_id not specified",
                            },
                        )

                elif action == "kill_flow":
                    flow_id = message.get("flow_id")
                    if flow_id:
                        success = self.delete_flow(flow_id)
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "flow_killed",
                                "success": success,
                                "flow_id": flow_id,
                            },
                        )
                    else:
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "error",
                                "message": "flow_id not specified",
                            },
                        )

                else:
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "error",
                            "message": f"Unknown action: {action}",
                        },
                    )
            else:
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "error",
                        "message": "Invalid message type",
                    },
                )

        except Exception as e:
            logger.error("Error handling message: %s", e)
            await self.send_response(
                websocket, {"type": "mitmproxy", "action": "error", "message": str(e)}
            )

    # State management
    async def get_state(self) -> dict:
        """Get mitmproxy state"""
        try:

            state = {
                "version": "mitmproxy",
                "proxy_port": self.proxy_port,
                "proxy_host": self.proxy_host,
                "backend_ip": self.backend_ip,
                "is_running": self.is_running,
                "device_id": self.device_id,
                "flows_count": len(self.get_flows()) if self.master_instance else 0,
                "su_available": self.su_available,
                "cert_installed": self.cert_installed,
                "proxy_configured": self.proxy_configured,
                "port_available": await self._check_port_available(self.proxy_port),
                "port_listening": self._check_port_listening(self.proxy_port),
            }

            return state
        except Exception as e:
            logger.error("Error getting state: %s", e)
            return {}

    async def set_proxy_port(self, port: int) -> bool:
        """Set proxy port (only if proxy is not running)"""
        if self.is_running:
            logger.warning("Cannot change port while proxy is running")
            return False

        if await self._check_port_available(port):
            self.proxy_port = port
            logger.info("Proxy port set to %s", port)
            return True
        logger.warning("Port %s is not available", port)
        return False

    # Certificate management methods (keep your existing implementation)
    async def generate_certificate(self) -> Optional[str]:
        """Generate mitmproxy certificate"""
        # Keep your existing implementation
        try:
            logger.info("Generating mitmproxy certificate")

            cert_path = os.path.join(self.certs_dir, "mitmproxy-ca-cert.pem")

            if os.path.exists(cert_path):
                logger.info("Certificate already exists at %s", cert_path)
                return cert_path

            # Create certificate using mitmproxy's certificate authority
            ca = certs.CertStore.from_store(self.data_dir, "mitmproxy", 2048)

            with open(cert_path, "wb") as f:
                f.write(ca.default_ca.to_pem())

            logger.info("Certificate generated at %s", cert_path)
            return cert_path

        except Exception as e:
            logger.error("Error generating certificate: %s", str(e))
            return None

    def _check_port_listening(self, port: int) -> bool:
        """Check if port is listening"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            return result == 0
        except Exception:
            return False

    async def _check_port_available(self, port: int) -> bool:
        """Check if port is available for binding"""
        try:
            # Use asyncio for non-blocking port check
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._check_port_sync, port)
        except Exception as e:
            logger.debug("Port %s is not available: %s", port, e)
            return False

    def _check_port_sync(self, port: int) -> bool:
        """Synchronous port check"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            # Set flags for port reuse
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            sock.bind(("0.0.0.0", port))
            sock.close()
            return True
        except Exception as e:
            logger.debug("Port %s is not available: %s", port, e)
            return False

    async def _safe_release_port(self):
        """Safely release the proxy port by waiting for natural release"""
        try:
            # Wait for natural port release with multiple attempts
            logger.info("Waiting for port %s to be released naturally", self.proxy_port)

            # Attempt 1: short wait
            await asyncio.sleep(1)
            if await self._check_port_available(self.proxy_port):
                logger.info(
                    "Port %s is now available after short wait", self.proxy_port
                )
                return

            # Attempt 2: medium wait
            logger.info("Port %s still in use, waiting longer...", self.proxy_port)
            await asyncio.sleep(3)
            if await self._check_port_available(self.proxy_port):
                logger.info(
                    "Port %s is now available after medium wait", self.proxy_port
                )
                return

            # Attempt 3: long wait
            logger.info("Port %s still in use, waiting even longer...", self.proxy_port)
            await asyncio.sleep(5)
            if await self._check_port_available(self.proxy_port):
                logger.info("Port %s is now available after long wait", self.proxy_port)
                return

            # If port is still in use, log warning and re-diagnose
            logger.warning(
                "Port %s is still in use after all waiting attempts", self.proxy_port
            )

        except Exception as e:
            logger.warning("Error in safe port release: %s", e)

    async def install_certificate(self, websocket: Optional[WebSocket] = None) -> bool:
        """Install certificate on device"""
        try:
            logger.info("Installing certificate on device %s", self.device_id)

            # Check su availability
            self.su_available = await check_su_availability(self.device_id)

            # Get backend container IP if not set
            if not self.backend_ip:
                self.backend_ip = await self._get_backend_ip()

            # Generate certificate if it doesn't exist
            cert_path = await self.generate_certificate()
            if not cert_path or not os.path.exists(cert_path):
                logger.error("Certificate not found")
                return False

            with open(cert_path, "rb") as f:
                cert_content = f.read()

            # Calculate correct hash using openssl
            temp_cert_file = f"/tmp/temp_cert_{int(time.time())}.pem"
            with open(temp_cert_file, "wb") as f:
                f.write(cert_content)

            # Use openssl to get subject_hash_old
            hash_cmd = f"openssl x509 -inform PEM -subject_hash_old -in {temp_cert_file} | head -1"
            process = await asyncio.create_subprocess_shell(
                hash_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                cert_hash = stdout.decode().strip()
                logger.info("Certificate hash (subject_hash_old): %s", cert_hash)
            else:
                # Fallback to old method
                cert_hash = hashlib.md5(cert_content).hexdigest()[:8]
                logger.warning(
                    "Failed to get subject_hash_old, using MD5 fallback: %s", cert_hash
                )

            # Remove temporary file
            os.unlink(temp_cert_file)

            device_cert_path = f"/data/local/tmp/mitmproxy-ca-cert-{cert_hash}.pem"

            stdout, stderr, returncode = await execute_adb_command(
                device_id=self.device_id, command=["push", cert_path, device_cert_path]
            )

            if returncode != 0:
                logger.error("Failed to push certificate: %s", stderr)
                return False

            # Check su availability
            if not self.su_available:
                logger.warning(
                    "su not available, cannot install certificate to system store"
                )
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "certificate_warning",
                        "message": (
                            "Certificate copied to device but cannot install "
                            "to system store without root access"
                        ),
                    },
                )
                return True  # Technically successful, but without system store installation

            system_cert_path = f"/system/etc/security/cacerts/{cert_hash}.0"

            # Check Android version for path selection
            version_stdout, _, _ = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="getprop ro.build.version.sdk_int",
            )

            try:
                sdk_version = int(version_stdout.strip())
                logger.info("Android SDK version: %s", sdk_version)

                # Android 14 (API 34) and above use APEX container
                if sdk_version >= 34:
                    logger.info(
                        "Android 14+ detected, certificate installation may "
                        "require additional steps"
                    )
                    system_cert_path = (
                        f"/apex/com.android.conscrypt/cacerts/{cert_hash}.0"
                    )

                    # Warn user
                    await self.send_response(
                        websocket,
                        {
                            "type": "mitmproxy",
                            "action": "certificate_warning",
                            "message": (
                                "Android 14+ detected. System certificate "
                                "installation may not work due to APEX containers. "
                                "Consider using Magisk modules."
                            ),
                        },
                    )
            except Exception:
                logger.warning(
                    "Could not determine Android version, using default path"
                )

            # Check existing certificates in system
            list_stdout, list_stderr, returncode = await execute_adb_shell(
                device_id=self.device_id,
                shell_command="su 0 ls -la " "system/etc/security/cacerts/ | head -10",
            )

            if returncode == 0:
                existing_certs = list_stdout.strip()
                logger.info("Existing system certificates: %s", existing_certs)
            else:
                logger.warning("Failed to list existing certificates: %s", list_stderr)

            # Mount system as RW if needed
            _, _, _ = await execute_adb_shell(
                device_id=self.device_id, shell_command="su 0 mount -o rw,remount /"
            )

            # Detailed diagnostics before installation
            logger.info("Installing certificate:")
            logger.info("  - Device cert path: %s", device_cert_path)
            logger.info("  - System cert path: %s", system_cert_path)
            logger.info("  - Certificate hash: %s", cert_hash)

            install_commands = [
                f"su 0 cp {device_cert_path} {system_cert_path}",
                f"su 0 chmod 644 {system_cert_path}",
                f"su 0 chown root:root {system_cert_path}",
            ]

            success_count = 0
            for i, cmd in enumerate(install_commands):
                logger.info("Executing install command %s/3: %s", i + 1, cmd)

                stdout, stderr, returncode = await execute_adb_shell(
                    device_id=self.device_id, shell_command=cmd
                )

                if returncode == 0:
                    success_count += 1
                    logger.info("Command %s succeeded: %s", i + 1, stdout.strip())
                else:
                    logger.error("Command %s failed: %s", i + 1, stderr)

            logger.info("Install commands: %s/3 successful", success_count)

            # Mount system back as RO
            _, _, _ = await execute_adb_shell(
                device_id=self.device_id, shell_command="su 0 mount -o ro,remount /"
            )

            # Verify that certificate is actually installed
            verify_stdout, verify_stderr, returncode = await execute_adb_shell(
                device_id=self.device_id,
                shell_command=f"su 0 ls -la {system_cert_path}",
            )

            if returncode == 0:
                file_info = verify_stdout.strip()
                logger.info("Certificate verification: %s", file_info)

                # Check that certificate exactly matches original
                compare_stdout, compare_stderr, returncode = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command=f"su 0 cat {system_cert_path}",
                )

                if returncode == 0:
                    installed_cert = compare_stdout.strip()
                    original_cert = cert_content.decode().strip()

                    if installed_cert == original_cert:
                        logger.info("Certificate content matches original")
                        self.cert_installed = True
                    else:
                        logger.error("Certificate content does not match original!")
                        logger.error("Original length: %s", len(original_cert))
                        logger.error("Installed length: %s", len(installed_cert))
                        logger.error(
                            "First 100 chars of installed: %s", installed_cert[:100]
                        )
                        self.cert_installed = False
                else:
                    logger.error(
                        "Failed to read installed certificate: %s", compare_stderr
                    )
                    self.cert_installed = False

                if self.cert_installed:
                    logger.info(
                        "Certificate successfully installed and verified at %s",
                        system_cert_path,
                    )

            else:
                logger.error("Certificate verification failed: %s", verify_stderr)
                self.cert_installed = False

            # Suggest reboot to activate certificate only if installation was successful
            if self.cert_installed:
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "certificate_installed_reboot_needed",
                        "message": "Certificate installed successfully. "
                        "Reboot is recommended to activate it.",
                        "reboot_available": True,
                    },
                )
                return True

            await self.send_response(
                websocket,
                {
                    "type": "mitmproxy",
                    "action": "certificate_error",
                    "message": "Certificate installation failed",
                },
            )
            return False

        except Exception as e:
            logger.error("Error installing certificate: %s", str(e))
            return False

    async def send_response(self, websocket: Optional[WebSocket], response_data: dict):
        """Send response through WebSocket"""
        try:
            if websocket is not None:
                await websocket.send_text(json.dumps(response_data))
            else:
                # For HTTP endpoints, just log the response
                logger.info("HTTP endpoint response: %s", response_data)
        except Exception as e:
            logger.error("Error sending response: %s", e)

    async def send_error(self, websocket: Optional[WebSocket], message: str):
        """Send error response through WebSocket"""
        try:
            if websocket is not None:
                await websocket.send_text(
                    json.dumps(
                        {"type": "mitmproxy", "action": "error", "message": message}
                    )
                )
            else:
                # For HTTP endpoints, just log the error
                logger.error("HTTP endpoint error: %s", message)
        except Exception as e:
            logger.error("Error sending error response: %s", e)

    async def configure_device_proxy(
        self, websocket: Optional[WebSocket] = None
    ) -> bool:
        """Configure proxy on device"""
        try:
            logger.info("Configuring proxy on device %s", self.device_id)

            # Check su availability
            self.su_available = await check_su_availability(self.device_id)

            # Get backend container IP if not set
            if not self.backend_ip:
                self.backend_ip = await self._get_backend_ip()

            # Use command from user requirements
            # Use real backend container IP
            proxy_setting = f"{self.backend_ip}:{self.proxy_port}"

            if self.su_available:
                # Use su for global proxy configuration
                cmd = f"su 0 settings put global http_proxy {proxy_setting}"
            else:
                # Try to configure without su
                cmd = f"settings put global http_proxy {proxy_setting}"
            _, stderr, returncode = await execute_adb_shell(
                device_id=self.device_id, shell_command=cmd
            )

            if returncode == 0:
                logger.info("Proxy configured successfully: %s", proxy_setting)

                self.proxy_configured = True

                # Check that setting was applied
                check_stdout, _, _ = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command="settings get global http_proxy",
                )
                current_proxy = check_stdout.strip()
                logger.info("Current proxy setting: %s", current_proxy)

                # Send updated port information
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "proxy_port_updated",
                        "proxy_port": self.proxy_port,
                        "backend_ip": self.backend_ip,
                        "proxy_setting": proxy_setting,
                    },
                )

                return True

            logger.error("Failed to configure proxy: %s", stderr)
            return False

        except Exception as e:
            logger.error("Error configuring proxy: %s", str(e))
            return False

    async def disable_device_proxy(self, websocket: Optional[WebSocket] = None) -> bool:
        """Disable proxy on device"""
        try:
            logger.info("Disabling proxy on device %s", self.device_id)

            # Check su availability
            self.su_available = await check_su_availability(self.device_id)

            # Use command to disable proxy
            if self.su_available:
                # Use su for global proxy configuration
                cmd = f"su 0 settings put global http_proxy :0"
            else:
                # Try to disable without su
                cmd = f"settings put global http_proxy :0"

            _, stderr, returncode = await execute_adb_shell(
                device_id=self.device_id, shell_command=cmd
            )

            if returncode == 0:
                logger.info("Proxy disabled successfully")

                self.proxy_configured = False

                # Check that setting was applied
                check_stdout, _, _ = await execute_adb_shell(
                    device_id=self.device_id,
                    shell_command="settings get global http_proxy",
                )

                current_proxy = check_stdout.strip()
                logger.info("Current proxy setting: %s", current_proxy)

                # Send response
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "proxy_disabled",
                        "success": True,
                        "message": "Proxy disabled successfully",
                    },
                )

                return True

            logger.error("Failed to disable proxy: %s", stderr)
            return False

        except Exception as e:
            logger.error("Error disabling proxy: %s", str(e))
            return False

    async def _initialize_backend_ip(self) -> None:
        """Initialize backend container IP address"""
        try:
            self.backend_ip = await self._get_backend_ip()
            logger.info("Backend IP initialized: %s", self.backend_ip)
        except Exception as e:
            logger.error("Error initializing backend IP: %s", e)
            self.backend_ip = None  # Fallback

    async def _get_backend_ip(self) -> str:
        """Get backend container IP address"""
        try:
            # Method 1: Get IP from hostname -I
            process = await asyncio.create_subprocess_shell(
                "hostname -I",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                # Get first IP address
                ips = stdout.decode().strip().split()
                if ips:
                    backend_ip = ips[0]
                    logger.info("Backend container IP: %s", backend_ip)
                    return backend_ip

            # Method 2: Read IP from /proc/net/route (default routing)
            try:
                with open("/proc/net/route", "r", encoding="utf-8") as f:
                    for line in f:
                        fields = line.split()
                        if (
                            len(fields) >= 8 and fields[1] == "00000000"
                        ):  # Default route
                            # Get interface IP
                            interface = fields[0]
                            grep_cmd = (
                                f"ip addr show {interface} | grep 'inet ' | "
                                "head -1 | awk '{print $2}' | cut -d/ -f1"
                            )
                            process = await asyncio.create_subprocess_shell(
                                grep_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            stdout, _ = await process.communicate()
                            if process.returncode == 0:
                                ip = stdout.decode().strip()
                                if ip and not ip.startswith("127."):
                                    logger.info(
                                        "Backend container IP from route: %s", ip
                                    )
                                    return ip
                            break
            except Exception:
                pass

            # Fallback to old value
            logger.warning("Could not determine backend IP, using fallback")
            return None

        except Exception as e:
            logger.error("Error getting backend IP: %s", str(e))
            return None  # Fallback


_mitmproxy_managers: Dict[str, MitmproxyManager] = {}
_manager_lock = asyncio.Lock()


async def get_mitmproxy_manager(device_id: str) -> MitmproxyManager:
    """Get MitmproxyManager instance for device"""
    async with _manager_lock:
        if device_id not in _mitmproxy_managers:
            logger.info("Creating new mitmproxy manager for device %s", device_id)
            _mitmproxy_managers[device_id] = MitmproxyManager(device_id)
        else:
            logger.info("Reusing existing mitmproxy manager for device %s", device_id)
        return _mitmproxy_managers[device_id]


async def cleanup_mitmproxy_manager(device_id: str):
    """Clean up MitmproxyManager instance for device"""
    async with _manager_lock:
        if device_id in _mitmproxy_managers:
            manager = _mitmproxy_managers[device_id]
            logger.info("Cleaning up mitmproxy manager for device %s", device_id)
            try:
                await manager.stop()
            except Exception as e:
                logger.error("Error stopping manager during cleanup: %s", e)
            del _mitmproxy_managers[device_id]
            logger.info("Cleaned up mitmproxy manager for device %s", device_id)
        else:
            logger.info(
                "No mitmproxy manager found for device %s during cleanup", device_id
            )
