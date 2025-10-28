import asyncio
import json
import logging
import os
import time
import socket
import hashlib
import base64
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from io import BytesIO
from fastapi import WebSocket

from mitmproxy import master, options, flow, io as mitmproxy_io, certs
from mitmproxy.tools.web.master import WebMaster
from mitmproxy import addons
from mitmproxy import log
from mitmproxy import optmanager
from mitmproxy.addons import errorcheck
from mitmproxy.addons import eventstore
from mitmproxy.addons import intercept
from mitmproxy.addons import readfile
from mitmproxy.addons import view
from mitmproxy.http import HTTPFlow
from mitmproxy.tcp import TCPFlow
from mitmproxy.udp import UDPFlow
from mitmproxy.dns import DNSFlow
from mitmproxy import flowfilter
from mitmproxy.utils.emoji import emoji
from mitmproxy.utils.strutils import always_str
from app.dynamic.utils.su_utils import check_su_availability

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

        # Get request content (decrypted for HTTPS)
        request_content = None
        try:
            # Try to get text content first
            request_content = flow_obj.request.get_text(strict=False)
            # If None or empty string, try to get content and decode
            if not request_content or request_content == "":
                # Get raw content
                raw_data = flow_obj.request.get_content(strict=False)
                if raw_data:
                    try:
                        # Try to decode as UTF-8
                        request_content = raw_data.decode("utf-8")
                    except (UnicodeDecodeError, AttributeError):
                        # If not UTF-8 text, encode as base64
                        request_content = base64.b64encode(raw_data).decode("utf-8")
        except Exception as e:
            logger.warning("Error getting request content: %s", e)
            try:
                # Fallback: try to get content
                raw_data = flow_obj.request.get_content(strict=False)
                if raw_data:
                    request_content = raw_data.decode("utf-8", errors="replace")
            except Exception:
                request_content = None

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

            # Get response content (decrypted for HTTPS)
            response_content = None
            try:
                # Try to get text content first
                response_content = flow_obj.response.get_text(strict=False)
                # If None or empty string, try to get content and decode
                if not response_content or response_content == "":
                    # Get raw content
                    raw_data = flow_obj.response.get_content(strict=False)
                    if raw_data:
                        try:
                            # Try to decode as UTF-8
                            response_content = raw_data.decode("utf-8")
                        except (UnicodeDecodeError, AttributeError):
                            # If not UTF-8 text, encode as base64
                            response_content = base64.b64encode(raw_data).decode(
                                "utf-8"
                            )
            except Exception as e:
                logger.warning("Error getting response content: %s", e)
                try:
                    # Fallback: try to get content
                    raw_data = flow_obj.response.get_content(strict=False)
                    if raw_data:
                        response_content = raw_data.decode("utf-8", errors="replace")
                except Exception:
                    response_content = None

            f["response"] = {
                "http_version": flow_obj.response.http_version,
                "status_code": flow_obj.response.status_code,
                "reason": flow_obj.response.reason,
                "headers": tuple(flow_obj.response.headers.items(True)),
                "contentLength": content_length,
                "contentHash": content_hash,
                "content": response_content,
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
            "timestamp_last": flow_obj.messages[-1].timestamp if flow_obj.messages else None,
        }
    elif isinstance(flow_obj, DNSFlow):
        f["request"] = flow_obj.request.to_json()
        if flow_obj.response:
            f["response"] = flow_obj.response.to_json()

    return f


class WebMaster(master.Master):

    def __init__(self, opts: options.Options, with_termlog: bool = True):
        super().__init__(opts, with_termlog=with_termlog)

        # Initialize callback lists FIRST
        self.flow_callbacks: List[Callable] = []
        self.event_callbacks: List[Callable] = []
        self.option_callbacks: List[Callable] = []

        # Initialize view and events
        self.view = view.View()
        self.view.sig_view_add.connect(self._sig_view_add)
        self.view.sig_view_remove.connect(self._sig_view_remove)
        self.view.sig_view_update.connect(self._sig_view_update)
        self.view.sig_view_refresh.connect(self._sig_view_refresh)

        self.events = eventstore.EventStore()
        self.events.sig_add.connect(self._sig_events_add)
        self.events.sig_refresh.connect(self._sig_events_refresh)

        self.options.changed.connect(self._sig_options_update)

        # Add default addons
        self.addons.add(*addons.default_addons())
        self.addons.add(
            intercept.Intercept(),
            readfile.ReadFileStdin(),
            self.view,
            self.events,
            errorcheck.ErrorCheck(),
        )

    def add_flow_callback(self, callback: Callable):
        """Add callback for flow events"""
        if not hasattr(self, "flow_callbacks"):
            self.flow_callbacks = []
        if callable(callback):
            self.flow_callbacks.append(callback)
        else:
            logger.warning("Invalid flow callback: %s is not callable", type(callback))

    def add_event_callback(self, callback: Callable):
        """Add callback for log events"""
        if not hasattr(self, "event_callbacks"):
            self.event_callbacks = []
        if callable(callback):
            self.event_callbacks.append(callback)
        else:
            logger.warning("Invalid event callback: %s is not callable", type(callback))

    def add_option_callback(self, callback: Callable):
        """Add callback for option changes"""
        if not hasattr(self, "option_callbacks"):
            self.option_callbacks = []
        if callable(callback):
            self.option_callbacks.append(callback)
        else:
            logger.warning(
                "Invalid option callback: %s is not callable", type(callback)
            )

    def _sig_view_add(self, **kwargs) -> None:
        flow_obj = kwargs.get('flow')
        if hasattr(self, "flow_callbacks") and flow_obj:
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/add", flow_obj)
                    else:
                        logger.warning(
                            "Flow callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in flow callback: %s", callback_error)

    def _sig_view_update(self, **kwargs) -> None:
        flow_obj = kwargs.get('flow')
        if hasattr(self, "flow_callbacks") and flow_obj:
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/update", flow_obj)
                    else:
                        logger.warning(
                            "Flow callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in flow callback: %s", callback_error)

    def _sig_view_remove(self, **kwargs) -> None:
        flow_obj = kwargs.get('flow')
        if hasattr(self, "flow_callbacks") and flow_obj:
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/remove", flow_obj)
                    else:
                        logger.warning(
                            "Flow callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in flow callback: %s", callback_error)

    def _sig_view_refresh(self) -> None:
        if hasattr(self, "flow_callbacks"):
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/refresh", None)
                    else:
                        logger.warning(
                            "Flow callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in flow callback: %s", callback_error)

    def _sig_events_add(self, entry: log.LogEntry) -> None:
        if hasattr(self, "event_callbacks"):
            for callback in self.event_callbacks:
                try:
                    if callable(callback):
                        callback("events/add", entry)
                    else:
                        logger.warning(
                            "Event callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in event callback: %s", callback_error)

    def _sig_events_refresh(self) -> None:
        if hasattr(self, "event_callbacks"):
            for callback in self.event_callbacks:
                try:
                    if callable(callback):
                        callback("events/refresh", None)
                    else:
                        logger.warning(
                            "Event callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in event callback: %s", callback_error)

    def _sig_options_update(self, updated: set[str]) -> None:
        if hasattr(self, "option_callbacks"):
            for callback in self.option_callbacks:
                try:
                    if callable(callback):
                        options_dict = optmanager.dump_dicts(self.options, updated)
                        callback("options/update", options_dict)
                    else:
                        logger.warning(
                            "Option callback is not callable: %s", type(callback)
                        )
                except Exception as callback_error:
                    logger.error("Error in option callback: %s", callback_error)


class MitmproxyManager:
    """Mitmproxy Manager"""

    def __init__(self, device_id: str):
        self.device_id = device_id

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

    async def _get_device(self):
        """Get Device instance for this device_id"""
        try:
            from app.dynamic.device_management.device_manager import (
                DeviceManager
            )

            device_manager = DeviceManager()
            return await device_manager.get_device(self.device_id)
        except Exception as device_error:
            logger.error("Error getting device %s: %s", self.device_id, device_error)
            return None

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
                    "Port %s is not available during initialization",
                    self.proxy_port
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
            flow_id = flow_obj.id if flow_obj else 'None'
            logger.debug(
                "Flow event: %s - %s", event_type, flow_id
            )

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
            msg = getattr(log_entry, 'msg', str(log_entry))
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
            else:
                # Start the proxy (will reuse master if it exists)
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
                "stop_proxy() called - master_instance: %s", self.master_instance is not None
            )
            if self.master_instance is None:
                logger.info("Master instance is already None, nothing to stop")
                return True

            # First disable the server, as recommended in GitHub issue #7237
            try:
                logger.info(
                    "stop_proxy() - master_instance: %s", self.master_instance is not None
                )
                if self.master_instance is not None:
                    logger.info(
                        "stop_proxy() - master_instance type: %s", type(self.master_instance)
                    )
                    logger.info(
                        "stop_proxy() - master_instance has options: %s",
                        hasattr(self.master_instance, 'options')
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
                                    "Error shutting down addon %s: %s", type(addon).__name__, addon_error
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
                        master_instance_ref is not None
                    )
                    if master_instance_ref is not None:
                        logger.info(
                            "master_instance_ref type: %s", type(master_instance_ref)
                        )
                        logger.info(
                            "master_instance_ref has options: %s",
                            hasattr(master_instance_ref, 'options')
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
                hasattr(master_instance_ref, 'event_loop'), event_loop
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
                    "Could not shutdown master instance (threadsafe): %s", shutdown_error
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
                                    "Error shutting down addon %s: %s", type(addon).__name__, addon_error
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
                        self.proxy_port, attempt + 1
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

    def update_flow(self, flow_obj: flow.Flow) -> bool:
        """Update a flow"""
        try:
            if self.master_instance and self.master_instance.view:
                self.master_instance.view.update([flow_obj])
                return True
            return False
        except Exception as e:
            logger.error("Error updating flow: %s", e)
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

    def add_flow(self, flow_obj: flow.Flow) -> bool:
        """Add a flow"""
        try:
            if self.master_instance and self.master_instance.view:
                self.master_instance.view.add([flow_obj])
                return True
            return False
        except Exception as e:
            logger.error("Error adding flow: %s", e)
            return False

    def resume_all_flows(self) -> int:
        """Resume all intercepted flows"""
        try:
            count = 0
            for flow_obj in self.get_flows():
                if flow_obj.intercepted:
                    flow_obj.resume()
                    count += 1
            return count
        except Exception as e:
            logger.error("Error resuming flows: %s", e)
            return 0

    def kill_all_flows(self) -> int:
        """Kill all killable flows"""
        try:
            count = 0
            for flow_obj in self.get_flows():
                if hasattr(flow_obj, "killable") and flow_obj.killable:
                    flow_obj.kill()
                    count += 1
            return count
        except Exception as e:
            logger.error("Error killing flows: %s", e)
            return 0

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

    def load_flows_from_dump(self, dump_content: bytes) -> bool:
        """Load flows from dump content"""
        try:
            if not self.master_instance:
                return False

            bio = BytesIO(dump_content)
            reader = mitmproxy_io.FlowReader(bio)

            flows_loaded = 0
            for flow_obj in reader.stream():
                self.add_flow(flow_obj)
                flows_loaded += 1

            logger.info("Loaded %s flows from dump", flows_loaded)
            return True

        except Exception as e:
            logger.error("Error loading flows from dump: %s", e)
            return False

    def export_flows_to_dump(self, flows: List[flow.Flow]) -> bytes:
        """Export flows to dump format"""
        try:
            bio = BytesIO()
            writer = mitmproxy_io.FlowWriter(bio)

            for flow_obj in flows:
                writer.add(flow_obj)

            bio.seek(0)
            return bio.getvalue()

        except Exception as e:
            logger.error("Error exporting flows to dump: %s", e)
            return b""

    async def export_traffic(self, export_format: str = "json") -> Any:
        """Export captured traffic in specified format"""
        try:
            flows = self.get_flows()

            if export_format == "json":
                flows_data = []
                for flow_obj in flows:
                    flows_data.append(flow_to_json(flow_obj))
                return flows_data

            if export_format == "har":
                har_data = self._convert_flows_to_har(flows)
                return har_data

            if export_format == "dump":
                return self.export_flows_to_dump(flows)

            raise ValueError(f"Unsupported export format: {export_format}")

        except Exception as e:
            logger.error("Error exporting traffic: %s", e)
            raise

    def _convert_flows_to_har(self, flows: List[flow.Flow]) -> dict:
        """Convert mitmproxy flows to HAR format"""
        try:
            har_data = {
                "log": {
                    "version": "1.2",
                    "creator": {"name": "MobSec Mitmproxy", "version": "1.0"},
                    "browser": {"name": "MobSec", "version": "1.0"},
                    "pages": [],
                    "entries": [],
                }
            }

            for flow_obj in flows:
                if hasattr(flow_obj, "request") and hasattr(flow_obj, "response"):
                    entry = self._convert_flow_to_har_entry(flow_obj)
                    if entry:
                        har_data["log"]["entries"].append(entry)

            return har_data

        except Exception as e:
            logger.error("Error converting flows to HAR: %s", e)
            return {"log": {"version": "1.2", "entries": []}}

    def _convert_flow_to_har_entry(self, flow_obj) -> Optional[dict]:
        """Convert a single flow to HAR entry format"""
        try:
            if not hasattr(flow_obj, "request") or not flow_obj.request:
                return None

            start_time = flow_obj.timestamp_created
            end_time = getattr(flow_obj, "timestamp_end", start_time)
            duration = (end_time - start_time) * 1000

            entry = {
                "startedDateTime": datetime.fromtimestamp(start_time).isoformat() + "Z",
                "time": duration,
                "request": self._convert_request_to_har(flow_obj.request),
                "response": (
                    self._convert_response_to_har(flow_obj.response)
                    if hasattr(flow_obj, "response") and flow_obj.response
                    else None
                ),
                "cache": {},
                "timings": {
                    "dns": -1,
                    "connect": -1,
                    "ssl": -1,
                    "send": 0,
                    "wait": duration,
                    "receive": 0,
                },
                "serverIPAddress": None,
                "connection": None,
            }

            if (
                hasattr(flow_obj, "server_conn")
                and flow_obj.server_conn
                and flow_obj.server_conn.peername
            ):
                entry["serverIPAddress"] = flow_obj.server_conn.peername[0]

            return entry

        except Exception as e:
            logger.error("Error converting flow to HAR entry: %s", e)
            return None

    def _convert_request_to_har(self, request) -> dict:
        """Convert mitmproxy request to HAR request format"""
        try:
            headers = []
            for name, value in request.headers.items(True):
                headers.append({"name": name, "value": str(value)})

            query_string = []
            if hasattr(request, "query") and request.query:
                for name, value in request.query.items():
                    query_string.append({"name": name, "value": str(value)})

            har_request = {
                "method": request.method,
                "url": f"{request.scheme}://{request.pretty_host}:{request.port}{request.path}",
                "httpVersion": request.http_version,
                "headers": headers,
                "queryString": query_string,
                "cookies": [],
                "headersSize": -1,
                "bodySize": len(request.raw_content) if request.raw_content else 0,
            }

            if request.raw_content:
                try:
                    content = request.get_text(strict=False)
                    if content is None:
                        content = request.get_content(strict=False)
                        if content:
                            content = content.hex()
                except:
                    content = request.get_content(strict=False)
                    if content:
                        content = content.hex()

                if content:
                    har_request["postData"] = {
                        "mimeType": request.headers.get("content-type", "text/plain"),
                        "text": content,
                        "params": [],
                    }

            return har_request

        except Exception as e:
            logger.error("Error converting request to HAR: %s", e)
            return {
                "method": "GET",
                "url": "",
                "httpVersion": "HTTP/1.1",
                "headers": [],
                "queryString": [],
                "cookies": [],
                "headersSize": -1,
                "bodySize": 0,
            }

    def _convert_response_to_har(self, response) -> dict:
        """Convert mitmproxy response to HAR response format"""
        try:
            headers = []
            for name, value in response.headers.items(True):
                headers.append({"name": name, "value": str(value)})

            har_response = {
                "status": response.status_code,
                "statusText": response.reason,
                "httpVersion": response.http_version,
                "headers": headers,
                "cookies": [],
                "content": {
                    "size": len(response.raw_content) if response.raw_content else 0,
                    "mimeType": response.headers.get("content-type", "text/plain"),
                    "text": None,
                    "encoding": None,
                },
                "redirectURL": "",
                "headersSize": -1,
                "bodySize": len(response.raw_content) if response.raw_content else 0,
            }

            if response.raw_content:
                try:
                    content = response.get_text(strict=False)
                    if content is None:
                        content = response.get_content(strict=False)
                        if content:
                            content = content.hex()
                except:
                    content = response.get_content(strict=False)
                    if content:
                        content = content.hex()

                if content:
                    har_response["content"]["text"] = content

            return har_response

        except Exception as e:
            logger.error("Error converting response to HAR: %s", e)
            return {
                "status": 200,
                "statusText": "OK",
                "httpVersion": "HTTP/1.1",
                "headers": [],
                "cookies": [],
                "content": {
                    "size": 0,
                    "mimeType": "text/plain",
                    "text": "",
                    "encoding": None,
                },
                "redirectURL": "",
                "headersSize": -1,
                "bodySize": 0,
            }

    async def clear_traffic(self) -> bool:
        """Clear all captured traffic"""
        try:
            return self.clear_flows()
        except Exception as e:
            logger.error("Error clearing traffic: %s", e)
            return False

    async def handle_message(self, websocket: WebSocket, data: str):
        """Handle WebSocket message"""
        try:
            message = json.loads(data)

            if "device_id" in message and message["device_id"] != self.device_id:
                expected = self.device_id
                got = message['device_id']
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
                    await self._check_su_availability()

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
                            "port": self.get_proxy_port(),
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
                            "port": self.get_proxy_port(),
                        },
                    )

                elif action == "force_cleanup":
                    self._cleanup_all_mitmproxy_processes()
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

                elif action == "reboot_device":
                    # Simple device reboot implementation
                    try:
                        cmd = f"adb -s {self.device_id} reboot"
                        process = await asyncio.create_subprocess_shell(
                            cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        _, stderr = await process.communicate()

                        success = process.returncode == 0
                        await self.send_response(
                            websocket,
                            {
                                "type": "mitmproxy",
                                "action": "device_rebooted",
                                "success": success,
                                "message": (
                                    "Device rebooted"
                                    if success
                                    else f"Reboot failed: {stderr.decode()}"
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

    # Options management
    def get_options(self) -> dict:
        """Get mitmproxy options"""
        try:
            if self.master_instance:
                return optmanager.dump_dicts(self.master_instance.options)
            return {}
        except Exception as e:
            logger.error("Error getting options: %s", e)
            return {}

    def update_options(self, options_dict: dict) -> bool:
        """Update mitmproxy options"""
        try:
            if self.master_instance:
                self.master_instance.options.update(**options_dict)
                return True
            return False
        except Exception as e:
            logger.error("Error updating options: %s", e)
            return False

    # State management
    async def get_state(self) -> dict:
        """Get mitmproxy state"""
        try:
            # Get proxy_configured from Device
            device = await self._get_device()
            proxy_configured = device.proxy_configured if device else False

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
                "proxy_configured": proxy_configured,
                "port_available": await self._check_port_available(self.proxy_port),
                "port_listening": self._check_port_listening(self.proxy_port),
            }

            if self.master_instance:
                state.update(
                    {
                        "contentViews": ["auto", "json", "xml", "html", "text"],
                        "platform": "linux",
                    }
                )

            return state
        except Exception as e:
            logger.error("Error getting state: %s", e)
            return {}

    def get_proxy_port(self) -> int:
        """Get current proxy port"""
        return self.proxy_port

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

    # Commands management
    def get_commands(self) -> dict:
        """Get available commands"""
        try:
            if self.master_instance and hasattr(self.master_instance, "commands"):
                commands = {}
                for name, cmd in self.master_instance.commands.commands.items():
                    commands[name] = {
                        "help": getattr(cmd, "help", ""),
                        "signature_help": getattr(cmd, "signature_help", lambda: "")(),
                    }
                return commands
            return {}
        except Exception as e:
            logger.error("Error getting commands: %s", e)
            return {}

    def execute_command(self, cmd: str, args: List[str] = None) -> Any:
        """Execute a command"""
        try:
            if self.master_instance and hasattr(self.master_instance, "commands"):
                args = args or []
                return self.master_instance.commands.call_strings(cmd, args)
            return None
        except Exception as e:
            logger.error("Error executing command %s: %s", cmd, e)
            raise

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

    async def _diagnose_port_usage(self, port: int):
        """Diagnose what's using the port (for debugging only)"""
        try:
            # Use asyncio to execute command
            process = await asyncio.create_subprocess_exec(
                "lsof",
                "-i",
                f":{port}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0 and stdout.strip():
                logger.info("Port %s is being used by:", port)
                logger.info(stdout.decode().strip())
            else:
                logger.info("lsof shows no processes using port %s", port)

        except Exception as e:
            logger.warning("Error diagnosing port usage: %s", e)

    async def _safe_release_port(self):
        """Safely release the proxy port by waiting for natural release"""
        try:
            # Diagnose what's using the port
            await self._diagnose_port_usage(self.proxy_port)

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
            await self._diagnose_port_usage(self.proxy_port)

        except Exception as e:
            logger.warning("Error in safe port release: %s", e)

    async def _cleanup_all_mitmproxy_processes(self):
        """Clean up all mitmproxy processes - simplified version"""
        try:
            logger.info("Skipping process cleanup - using natural port release")
            # Just wait for natural port release
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("Error in cleanup: %s", e)

    async def install_certificate(self, websocket: Optional[WebSocket] = None) -> bool:
        """Install certificate on device"""
        try:
            logger.info("Installing certificate on device %s", self.device_id)

            # Check su availability
            await self._check_su_availability()

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

            # Copy certificate to device
            push_cmd = f"adb -s {self.device_id} push {cert_path} {device_cert_path}"
            process = await asyncio.create_subprocess_shell(
                push_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error("Failed to push certificate: %s", stderr.decode())
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

            # Additional su access verification before installation
            test_su_cmd = f"adb -s {self.device_id} shell su 0 id"
            test_process = await asyncio.create_subprocess_shell(
                test_su_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            test_stdout, test_stderr = await test_process.communicate()

            if test_process.returncode != 0 or "root" not in test_stdout.decode():
                logger.error("su access verification failed: %s", test_stderr.decode())
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "certificate_error",
                        "message": "Root access required but not available",
                    },
                )
                return False

            system_cert_path = f"/system/etc/security/cacerts/{cert_hash}.0"

            # Check Android version for path selection
            version_cmd = (
                f"adb -s {self.device_id} shell getprop ro.build.version.sdk_int"
            )
            version_process = await asyncio.create_subprocess_shell(
                version_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            version_stdout, _ = await version_process.communicate()

            try:
                sdk_version = int(version_stdout.decode().strip())
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
            list_certs_cmd = (
                f"adb -s {self.device_id} shell su 0 ls -la "
                "/system/etc/security/cacerts/ | head -10"
            )
            list_process = await asyncio.create_subprocess_shell(
                list_certs_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            list_stdout, list_stderr = await list_process.communicate()

            if list_process.returncode == 0:
                existing_certs = list_stdout.decode().strip()
                logger.info("Existing system certificates: %s", existing_certs)
            else:
                logger.warning(
                    "Failed to list existing certificates: %s", list_stderr.decode()
                )

            # Mount system as RW if needed
            mount_rw_cmd = f"adb -s {self.device_id} shell su 0 mount -o rw,remount /"
            mount_process = await asyncio.create_subprocess_shell(
                mount_rw_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await mount_process.communicate()

            # Detailed diagnostics before installation
            logger.info("Installing certificate:")
            logger.info("  - Device cert path: %s", device_cert_path)
            logger.info("  - System cert path: %s", system_cert_path)
            logger.info("  - Certificate hash: %s", cert_hash)

            install_commands = [
                f"adb -s {self.device_id} shell su 0 cp {device_cert_path} {system_cert_path}",
                f"adb -s {self.device_id} shell su 0 chmod 644 {system_cert_path}",
                f"adb -s {self.device_id} shell su 0 chown root:root {system_cert_path}",
            ]

            success_count = 0
            for i, cmd in enumerate(install_commands):
                logger.info("Executing install command %s/3: %s", i + 1, cmd)
                process = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    success_count += 1
                    logger.info(
                        "Command %s succeeded: %s", i + 1, stdout.decode().strip()
                    )
                else:
                    logger.error("Command %s failed: %s", i + 1, stderr.decode())

            logger.info("Install commands: %s/3 successful", success_count)

            # Mount system back as RO
            mount_ro_cmd = f"adb -s {self.device_id} shell su 0 mount -o ro,remount /"
            mount_ro_process = await asyncio.create_subprocess_shell(
                mount_ro_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await mount_ro_process.communicate()

            # Verify that certificate is actually installed
            verify_cmd = f"adb -s {self.device_id} shell su 0 ls -la {system_cert_path}"
            verify_process = await asyncio.create_subprocess_shell(
                verify_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            verify_stdout, verify_stderr = await verify_process.communicate()

            if verify_process.returncode == 0:
                file_info = verify_stdout.decode().strip()
                logger.info("Certificate verification: %s", file_info)

                # Check that certificate exactly matches original
                compare_cmd = (
                    f"adb -s {self.device_id} shell su 0 cat {system_cert_path}"
                )
                compare_process = await asyncio.create_subprocess_shell(
                    compare_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                compare_stdout, compare_stderr = await compare_process.communicate()

                if compare_process.returncode == 0:
                    installed_cert = compare_stdout.decode().strip()
                    original_cert = cert_content.decode().strip()

                    if installed_cert == original_cert:
                        logger.info("✅ Certificate content matches original")
                        self.cert_installed = True
                    else:
                        logger.error("❌ Certificate content does not match original!")
                        logger.error("Original length: %s", len(original_cert))
                        logger.error("Installed length: %s", len(installed_cert))
                        logger.error(
                            "First 100 chars of installed: %s", installed_cert[:100]
                        )
                        self.cert_installed = False
                else:
                    logger.error(
                        "Failed to read installed certificate: %s", compare_stderr.decode()
                    )
                    self.cert_installed = False

                # Additionally check owner and permissions
                if self.cert_installed:
                    stat_cmd = (
                        f"adb -s {self.device_id} shell su 0 stat {system_cert_path}"
                    )
                    stat_process = await asyncio.create_subprocess_shell(
                        stat_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stat_stdout, _ = await stat_process.communicate()
                    if stat_process.returncode == 0:
                        logger.info(
                            "Certificate file stats: %s", stat_stdout.decode().strip()
                        )

                if self.cert_installed:
                    logger.info(
                        "✅ Certificate successfully installed and verified at %s", system_cert_path
                    )

            else:
                logger.error(
                    "❌ Certificate verification failed: %s", verify_stderr.decode()
                )
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
            await self._check_su_availability()

            # Get backend container IP if not set
            if not self.backend_ip:
                self.backend_ip = await self._get_backend_ip()

            # Use command from user requirements
            # Use real backend container IP
            proxy_setting = f"{self.backend_ip}:{self.proxy_port}"

            if self.su_available:
                # Use su for global proxy configuration
                cmd = (
                    f"adb -s {self.device_id} shell su 0 "
                    f"settings put global http_proxy {proxy_setting}"
                )
            else:
                # Try to configure without su
                cmd = (
                    f"adb -s {self.device_id} shell "
                    f"settings put global http_proxy {proxy_setting}"
                )

            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("Proxy configured successfully: %s", proxy_setting)

                # Mark proxy as configured in Device
                device = await self._get_device()
                if device:
                    device.proxy_configured = True

                # Check that setting was applied
                check_cmd = (
                    f"adb -s {self.device_id} shell settings get global http_proxy"
                )
                check_process = await asyncio.create_subprocess_shell(
                    check_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                check_stdout, _ = await check_process.communicate()

                current_proxy = check_stdout.decode().strip()
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

            logger.error("Failed to configure proxy: %s", stderr.decode())
            return False

        except Exception as e:
            logger.error("Error configuring proxy: %s", str(e))
            return False

    async def disable_device_proxy(self, websocket: Optional[WebSocket] = None) -> bool:
        """Disable proxy on device"""
        try:
            logger.info("Disabling proxy on device %s", self.device_id)

            # Check su availability
            await self._check_su_availability()

            # Use command to disable proxy
            if self.su_available:
                # Use su for global proxy configuration
                cmd = f"adb -s {self.device_id} shell su 0 settings put global http_proxy 0"
            else:
                # Try to disable without su
                cmd = f"adb -s {self.device_id} shell settings put global http_proxy 0"

            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info("Proxy disabled successfully")

                # Mark proxy as not configured in Device
                device = await self._get_device()
                if device:
                    device.proxy_configured = False

                # Check that setting was applied
                check_cmd = (
                    f"adb -s {self.device_id} shell settings get global http_proxy"
                )
                check_process = await asyncio.create_subprocess_shell(
                    check_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                check_stdout, _ = await check_process.communicate()

                current_proxy = check_stdout.decode().strip()
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

            logger.error("Failed to disable proxy: %s", stderr.decode())
            return False

        except Exception as e:
            logger.error("Error disabling proxy: %s", str(e))
            return False

    async def _get_emulator_name_by_device_id(self) -> Optional[str]:
        """Determines emulator name by device_id"""
        try:
            # Import EmulatorManager
            from app.dynamic.emulator_manager import EmulatorManager

            # Create emulator manager instance
            redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
            emulators_path = "/app/emulators"
            emulator_manager = EmulatorManager(redis_url, emulators_path)

            # Get list of emulators
            emulators = await emulator_manager.list_emulators()

            # Look for emulator with matching IP
            for emulator in emulators:
                if emulator["status"] == "running" and emulator.get("container_id"):
                    # Get container IP
                    container_ip = emulator_manager._get_container_ip(
                        emulator["container_id"]
                    )
                    if container_ip and (
                        container_ip in self.device_id
                        or (self.device_ip and container_ip == self.device_ip)
                    ):
                        logger.info(
                            "Found emulator %s for device %s", emulator['name'], self.device_id
                        )
                        return emulator["name"]

            logger.info("Device %s is not a Docker emulator", self.device_id)
            return None

        except Exception as e:
            logger.warning("Could not determine emulator name: %s", str(e))
            return None

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

    async def _get_device_ip(self) -> None:
        """Get device IP address"""
        try:
            # Try to get IP from ADB
            cmd = f"adb -s {self.device_id} shell ip route get 1.1.1.1"
            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                # Parse output to get IP
                parts = output.split()
                if "src" in parts:
                    src_index = parts.index("src")
                    if src_index + 1 < len(parts):
                        self.device_ip = parts[src_index + 1]
                        logger.info("Device IP: %s", self.device_ip)
                        return

            # Alternative method
            cmd = f"adb -s {self.device_id} shell ifconfig | grep 'inet addr'"
            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            if process.returncode == 0:
                # Look for first non-localhost IP
                lines = stdout.decode().split("\n")
                for line in lines:
                    if "inet addr:" in line and "127.0.0.1" not in line:
                        ip_part = line.split("inet addr:")[1].split()[0]
                        self.device_ip = ip_part
                        logger.info("Device IP (alternative): %s", self.device_ip)
                        return

            logger.warning("Could not determine device IP")

        except Exception as e:
            logger.error("Error getting device IP: %s", str(e))

    async def _check_su_availability(self) -> None:
        """Check su availability on device"""
        try:
            self.su_available = await check_su_availability(self.device_id)
            if self.su_available:
                logger.info("su is available on device")
            else:
                logger.info("su is not available on device")
        except Exception as e:
            logger.error("Error checking su availability: %s", str(e))
            self.su_available = False

    async def _check_certificate_status(self) -> None:
        """Check certificate installation status"""
        try:
            self.cert_installed = False  # By default consider not installed

            # Check su availability
            await self._check_su_availability()

            if not self.su_available:
                logger.info("Cannot check certificate status without root access")
                return

            # First check for local mitmproxy certificate
            cert_path = os.path.join(self.certs_dir, "mitmproxy-ca-cert.pem")
            if not os.path.exists(cert_path):
                logger.info("Local mitmproxy certificate not found")
                return

            # Get local certificate hash
            with open(cert_path, "rb") as f:
                cert_content = f.read()

            # Get correct hash
            temp_cert_file = f"/tmp/temp_cert_check_{int(time.time())}.pem"
            with open(temp_cert_file, "wb") as f:
                f.write(cert_content)

            hash_cmd = f"openssl x509 -inform PEM -subject_hash_old -in {temp_cert_file} | head -1"
            process = await asyncio.create_subprocess_shell(
                hash_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                cert_hash = stdout.decode().strip()
                os.unlink(temp_cert_file)

                # Check if certificate with this hash exists in system
                system_cert_path = f"/system/etc/security/cacerts/{cert_hash}.0"
                check_cmd = (
                    f"adb -s {self.device_id} shell su 0 test -f "
                    f"{system_cert_path} && echo 'exists'"
                )
                check_process = await asyncio.create_subprocess_shell(
                    check_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                check_stdout, _ = await check_process.communicate()

                if check_process.returncode == 0 and "exists" in check_stdout.decode():
                    # Check that content matches
                    read_cmd = (
                        f"adb -s {self.device_id} shell su 0 cat {system_cert_path}"
                    )
                    read_process = await asyncio.create_subprocess_shell(
                        read_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    read_stdout, _ = await read_process.communicate()

                    if read_process.returncode == 0:
                        installed_cert = read_stdout.decode().strip()
                        original_cert = cert_content.decode().strip()

                        if installed_cert == original_cert:
                            self.cert_installed = True
                            logger.info(
                                "✅ Mitmproxy certificate verified at %s", system_cert_path
                            )
                        else:
                            logger.warning(
                                "❌ Certificate content mismatch at %s", system_cert_path
                            )
                    else:
                        logger.warning(
                            "❌ Cannot read certificate at %s", system_cert_path
                        )
                else:
                    logger.info("❌ Certificate not found at %s", system_cert_path)
            else:
                os.unlink(temp_cert_file)
                logger.warning("Failed to get certificate hash: %s", stderr.decode())

        except Exception as e:
            logger.error("Error checking certificate status: %s", str(e))
            self.cert_installed = False


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
                await manager.stop(cleanup=True)
            except Exception as e:
                logger.error("Error stopping manager during cleanup: %s", e)
            del _mitmproxy_managers[device_id]
            logger.info("Cleaned up mitmproxy manager for device %s", device_id)
        else:
            logger.info(
                "No mitmproxy manager found for device %s during cleanup", device_id
            )
