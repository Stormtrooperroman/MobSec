import asyncio
import json
import logging
import os
import tempfile
import threading
import time
import socket
import subprocess
import ssl
import hashlib
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from io import BytesIO
from fastapi import WebSocket

from mitmproxy import master, options, http, flow, io as mitmproxy_io
from mitmproxy.addons import core
from mitmproxy.tools.web.master import WebMaster
from mitmproxy import addons
from mitmproxy import log
from mitmproxy import optmanager
from mitmproxy.addons import errorcheck
from mitmproxy.addons import eventstore
from mitmproxy.addons import intercept
from mitmproxy.addons import readfile
from mitmproxy.addons import view
from mitmproxy.addons.proxyserver import Proxyserver
from mitmproxy.tools.web import app
from mitmproxy.tools.web import static_viewer
from mitmproxy.tools.web import webaddons
from mitmproxy.http import HTTPFlow
from mitmproxy.tcp import TCPFlow
from mitmproxy.udp import UDPFlow
from mitmproxy.dns import DNSFlow
from mitmproxy import flowfilter
from mitmproxy.utils.emoji import emoji
from mitmproxy.utils.strutils import always_str

logger = logging.getLogger(__name__)


def cert_to_json(certs) -> dict | None:
    """Convert certificate to JSON format"""
    if not certs:
        return None
    cert = certs[0]
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


def flow_to_json(flow: flow.Flow) -> dict:
    """
    Convert flow to JSON format
    """
    f = {
        "id": flow.id,
        "intercepted": flow.intercepted,
        "is_replay": flow.is_replay,
        "type": flow.type,
        "modified": flow.modified(),
        "marked": emoji.get(flow.marked, "🔴") if flow.marked else "",
        "comment": flow.comment,
        "timestamp_created": flow.timestamp_created,
    }

    if flow.client_conn:
        f["client_conn"] = {
            "id": flow.client_conn.id,
            "peername": flow.client_conn.peername,
            "sockname": flow.client_conn.sockname,
            "tls_established": flow.client_conn.tls_established,
            "cert": cert_to_json(flow.client_conn.certificate_list),
            "sni": flow.client_conn.sni,
            "cipher": flow.client_conn.cipher,
            "alpn": always_str(flow.client_conn.alpn, "ascii", "backslashreplace"),
            "tls_version": flow.client_conn.tls_version,
            "timestamp_start": flow.client_conn.timestamp_start,
            "timestamp_tls_setup": flow.client_conn.timestamp_tls_setup,
            "timestamp_end": flow.client_conn.timestamp_end,
        }

    if flow.server_conn:
        f["server_conn"] = {
            "id": flow.server_conn.id,
            "peername": flow.server_conn.peername,
            "sockname": flow.server_conn.sockname,
            "address": flow.server_conn.address,
            "tls_established": flow.server_conn.tls_established,
            "cert": cert_to_json(flow.server_conn.certificate_list),
            "sni": flow.server_conn.sni,
            "cipher": flow.server_conn.cipher,
            "alpn": always_str(flow.server_conn.alpn, "ascii", "backslashreplace"),
            "tls_version": flow.server_conn.tls_version,
            "timestamp_start": flow.server_conn.timestamp_start,
            "timestamp_tcp_setup": flow.server_conn.timestamp_tcp_setup,
            "timestamp_tls_setup": flow.server_conn.timestamp_tls_setup,
            "timestamp_end": flow.server_conn.timestamp_end,
        }

    if flow.error:
        f["error"] = flow.error.get_state()

    if isinstance(flow, HTTPFlow):
        content_length: int | None
        content_hash: str | None

        if flow.request.raw_content is not None:
            content_length = len(flow.request.raw_content)
            content_hash = hashlib.sha256(flow.request.raw_content).hexdigest()
        else:
            content_length = None
            content_hash = None
        f["request"] = {
            "method": flow.request.method,
            "scheme": flow.request.scheme,
            "host": flow.request.host,
            "port": flow.request.port,
            "path": flow.request.path,
            "http_version": flow.request.http_version,
            "headers": tuple(flow.request.headers.items(True)),
            "contentLength": content_length,
            "contentHash": content_hash,
            "timestamp_start": flow.request.timestamp_start,
            "timestamp_end": flow.request.timestamp_end,
            "pretty_host": flow.request.pretty_host,
        }
        if flow.response:
            if flow.response.raw_content is not None:
                content_length = len(flow.response.raw_content)
                content_hash = hashlib.sha256(flow.response.raw_content).hexdigest()
            else:
                content_length = None
                content_hash = None
            f["response"] = {
                "http_version": flow.response.http_version,
                "status_code": flow.response.status_code,
                "reason": flow.response.reason,
                "headers": tuple(flow.response.headers.items(True)),
                "contentLength": content_length,
                "contentHash": content_hash,
                "timestamp_start": flow.response.timestamp_start,
                "timestamp_end": flow.response.timestamp_end,
            }
            if flow.response.data.trailers:
                f["response"]["trailers"] = tuple(
                    flow.response.data.trailers.items(True)
                )

        if flow.websocket:
            f["websocket"] = {
                "messages_meta": {
                    "contentLength": sum(
                        len(x.content) for x in flow.websocket.messages
                    ),
                    "count": len(flow.websocket.messages),
                    "timestamp_last": (
                        flow.websocket.messages[-1].timestamp
                        if flow.websocket.messages
                        else None
                    ),
                },
                "closed_by_client": flow.websocket.closed_by_client,
                "close_code": flow.websocket.close_code,
                "close_reason": flow.websocket.close_reason,
                "timestamp_end": flow.websocket.timestamp_end,
            }
    elif isinstance(flow, (TCPFlow, UDPFlow)):
        f["messages_meta"] = {
            "contentLength": sum(len(x.content) for x in flow.messages),
            "count": len(flow.messages),
            "timestamp_last": flow.messages[-1].timestamp if flow.messages else None,
        }
    elif isinstance(flow, DNSFlow):
        f["request"] = flow.request.to_json()
        if flow.response:
            f["response"] = flow.response.to_json()

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
            logger.warning(f"Invalid flow callback: {type(callback)} is not callable")

    def add_event_callback(self, callback: Callable):
        """Add callback for log events"""
        if not hasattr(self, "event_callbacks"):
            self.event_callbacks = []
        if callable(callback):
            self.event_callbacks.append(callback)
        else:
            logger.warning(f"Invalid event callback: {type(callback)} is not callable")

    def add_option_callback(self, callback: Callable):
        """Add callback for option changes"""
        if not hasattr(self, "option_callbacks"):
            self.option_callbacks = []
        if callable(callback):
            self.option_callbacks.append(callback)
        else:
            logger.warning(f"Invalid option callback: {type(callback)} is not callable")

    def _sig_view_add(self, flow: flow.Flow) -> None:
        if hasattr(self, "flow_callbacks"):
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/add", flow)
                    else:
                        logger.warning(
                            f"Flow callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in flow callback: {e}")

    def _sig_view_update(self, flow: flow.Flow) -> None:
        if hasattr(self, "flow_callbacks"):
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/update", flow)
                    else:
                        logger.warning(
                            f"Flow callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in flow callback: {e}")

    def _sig_view_remove(self, flow: flow.Flow, index: int) -> None:
        if hasattr(self, "flow_callbacks"):
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/remove", flow)
                    else:
                        logger.warning(
                            f"Flow callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in flow callback: {e}")

    def _sig_view_refresh(self) -> None:
        if hasattr(self, "flow_callbacks"):
            for callback in self.flow_callbacks:
                try:
                    if callable(callback):
                        callback("flows/refresh", None)
                    else:
                        logger.warning(
                            f"Flow callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in flow callback: {e}")

    def _sig_events_add(self, entry: log.LogEntry) -> None:
        if hasattr(self, "event_callbacks"):
            for callback in self.event_callbacks:
                try:
                    if callable(callback):
                        callback("events/add", entry)
                    else:
                        logger.warning(
                            f"Event callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")

    def _sig_events_refresh(self) -> None:
        if hasattr(self, "event_callbacks"):
            for callback in self.event_callbacks:
                try:
                    if callable(callback):
                        callback("events/refresh", None)
                    else:
                        logger.warning(
                            f"Event callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")

    def _sig_options_update(self, updated: set[str]) -> None:
        if hasattr(self, "option_callbacks"):
            for callback in self.option_callbacks:
                try:
                    if callable(callback):
                        options_dict = optmanager.dump_dicts(self.options, updated)
                        callback("options/update", options_dict)
                    else:
                        logger.warning(
                            f"Option callback is not callable: {type(callback)}"
                        )
                except Exception as e:
                    logger.error(f"Error in option callback: {e}")


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
                    logger.warning(f"Error shutting down existing master: {e}")
                logger.info("Setting master_instance to None in _initialize_master()")
                self.master_instance = None

            # Check port availability before initialization
            if not await self._check_port_available(self.proxy_port):
                logger.warning(
                    f"Port {self.proxy_port} is not available during initialization"
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
                                logger.info(f"Found available port {test_port}")
                                self.proxy_port = test_port
                                break
                        else:
                            raise RuntimeError(
                                f"Could not find any available port in range 8082-8100"
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

            logger.info(f"Mitmproxy master initialized on port {self.proxy_port}")
        except Exception as e:
            logger.error(f"Error initializing mitmproxy master: {e}")
            raise

    def _handle_flow_event(self, event_type: str, flow_obj):
        """Handle flow events"""
        try:
            # Log the event
            logger.debug(
                f"Flow event: {event_type} - {flow_obj.id if flow_obj else 'None'}"
            )

            if hasattr(self, "_active_websockets") and self._active_websockets:
                import json

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
                        except Exception as e:
                            logger.warning(
                                f"Failed to send flow event to WebSocket: {e}"
                            )

        except Exception as e:
            logger.error(f"Error in flow event handler: {e}")

    def _handle_log_event(self, event_type: str, log_entry):
        """Handle log events"""
        try:
            # Just log the event
            logger.debug(
                f"Log event: {event_type} - {getattr(log_entry, 'msg', str(log_entry))}"
            )
        except Exception as e:
            logger.error(f"Error in log event handler: {e}")

    def _handle_option_event(self, event_type: str, options_dict):
        """Handle option change events"""
        try:
            # Just log the event
            logger.debug(f"Option event: {event_type} - {options_dict}")
        except Exception as e:
            logger.error(f"Error in option event handler: {e}")

    def add_websocket(self, websocket):
        """Add WebSocket connection for real-time updates"""
        if not hasattr(self, "_active_websockets"):
            self._active_websockets = set()
        self._active_websockets.add(websocket)
        logger.info(
            f"Added WebSocket for device {self.device_id}, total: {len(self._active_websockets)}"
        )

    def remove_websocket(self, websocket):
        """Remove WebSocket connection"""
        if hasattr(self, "_active_websockets"):
            self._active_websockets.discard(websocket)
            logger.info(
                f"Removed WebSocket for device {self.device_id}, total: {len(self._active_websockets)}"
            )

    async def start(self) -> bool:
        """Start mitmproxy manager"""
        if self.is_running:
            return True

        try:
            self.is_running = True
            logger.info(f"Starting Mitmproxy manager for device {self.device_id}")

            # Always initialize a new master instance
            await self._initialize_master()

            # Initialize backend_ip if it's not set
            if not self.backend_ip or self.backend_ip == "172.19.0.1":
                # Create a task for asynchronous IP retrieval
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If event loop is running, create a task
                        asyncio.create_task(self._initialize_backend_ip())
                    else:
                        # If event loop is not running, start a new one
                        asyncio.run(self._initialize_backend_ip())
                except Exception as e:
                    logger.warning(f"Could not initialize backend IP: {e}")

            return True

        except Exception as e:
            logger.error(f"Error starting Mitmproxy manager: {str(e)}")
            self.is_running = False
            return False

    async def stop(self) -> bool:
        """Stop mitmproxy manager"""
        try:
            logger.info(f"Stopping Mitmproxy manager for device {self.device_id}")

            # Use safe shutdown method that follows recommendations from GitHub issue #7237
            logger.info("Calling stop_proxy_threadsafe() instead of stop_proxy()")
            await self.stop_proxy_threadsafe()
            self.is_running = False

            # Reset master instance for complete cleanup
            logger.info("Setting master_instance to None in stop()")
            self.master_instance = None

            # Safely release the port
            await self._safe_release_port()

            logger.info("Mitmproxy manager stopped successfully")
            return True

        except Exception as e:
            logger.error(f"Error stopping Mitmproxy manager: {str(e)}")
            return False

    async def start_proxy(self) -> bool:
        """Start the proxy server"""
        try:
            # Always create a new master instance to avoid event loop issues
            # _initialize_master() will automatically release the port or find a free one
            await self._initialize_master()

            if self.proxy_task and not self.proxy_task.done():
                logger.info("Proxy is already running")
                return True

            logger.info(f"Starting proxy on {self.proxy_host}:{self.proxy_port}")

            # Create an asynchronous task to start the proxy
            self.proxy_task = asyncio.create_task(self._run_proxy())

            # Wait a bit for the proxy to start
            await asyncio.sleep(2)

            # Check if proxy is listening
            if self._check_port_listening(self.proxy_port):
                logger.info(f"Proxy started successfully on port {self.proxy_port}")
                return True
            else:
                logger.error("Proxy failed to start")
                return False

        except Exception as e:
            logger.error(f"Error starting proxy: {str(e)}")
            return False

    async def stop_proxy(self) -> bool:
        """Stop the proxy server"""
        try:
            logger.info(
                f"stop_proxy() called - master_instance: {self.master_instance is not None}"
            )
            if self.master_instance is None:
                logger.info("Master instance is already None, nothing to stop")
                return True

            # First disable the server, as recommended in GitHub issue #7237
            try:
                logger.info(
                    f"stop_proxy() - master_instance: {self.master_instance is not None}"
                )
                if self.master_instance is not None:
                    logger.info(
                        f"stop_proxy() - master_instance type: {type(self.master_instance)}"
                    )
                    logger.info(
                        f"stop_proxy() - master_instance has options: {hasattr(self.master_instance, 'options')}"
                    )

                logger.info("Disabling server before shutdown")
                # Update options to disable the server
                self.master_instance.options.update(server=False)
                logger.info("Server disabled")
            except Exception as server_error:
                logger.warning(f"Could not disable server: {server_error}")

            # Stop the master instance
            try:
                logger.info("Shutting down master instance")
                self.master_instance.shutdown()
                logger.info("Master instance shutdown")
            except Exception as shutdown_error:
                logger.warning(f"Could not shutdown master instance: {shutdown_error}")

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
                                    f"Error shutting down addon {type(addon).__name__}: {addon_error}"
                                )
            except Exception as e:
                logger.warning(f"Error shutting down addons: {e}")

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
            logger.error(f"Error stopping proxy: {str(e)}")
            return False

    async def stop_proxy_threadsafe(self) -> bool:
        """Stop the proxy server from another thread safely"""
        try:
            logger.info(
                f"stop_proxy_threadsafe() called - master_instance: {self.master_instance is not None}"
            )
            if self.master_instance is None:
                logger.info("Master instance is already None, nothing to stop")
                return True

            # Save reference to master_instance at function creation time
            master_instance_ref = self.master_instance

            # Use call_soon_threadsafe for safe call from another thread
            def stop_server():
                try:
                    logger.info(
                        f"stop_server() called - master_instance_ref: {master_instance_ref is not None}"
                    )
                    if master_instance_ref is not None:
                        logger.info(
                            f"master_instance_ref type: {type(master_instance_ref)}"
                        )
                        logger.info(
                            f"master_instance_ref has options: {hasattr(master_instance_ref, 'options')}"
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
                    logger.warning(f"Could not disable server (threadsafe): {e}")

            logger.info(
                f"stop_server() called: {hasattr(master_instance_ref, 'event_loop')} {master_instance_ref.event_loop if master_instance_ref else None}"
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
                        f"Could not schedule server stop in event loop: {loop_error}"
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
                    f"Could not shutdown master instance (threadsafe): {shutdown_error}"
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
                                    f"Error shutting down addon {type(addon).__name__}: {addon_error}"
                                )
            except Exception as e:
                logger.warning(f"Error shutting down addons: {e}")

            # Reset master instance for creating a new one on next startup
            logger.info("Setting master_instance to None in stop_proxy_threadsafe()")
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
                logger.info(f"Port release attempt {attempt + 1}/3")
                await self._safe_release_port()
                if await self._check_port_available(self.proxy_port):
                    logger.info(
                        f"Port {self.proxy_port} successfully released on attempt {attempt + 1}"
                    )
                    break
                time.sleep(2)

            logger.info("Proxy stopped (threadsafe)")
            return True

        except Exception as e:
            logger.error(f"Error stopping proxy (threadsafe): {str(e)}")
            return False

    async def _run_proxy(self):
        """Run proxy asynchronously"""
        try:
            if self.master_instance:
                # Start master in current event loop
                await self.master_instance.run()
        except Exception as e:
            logger.error(f"Error in proxy task: {str(e)}")

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
            logger.error(f"Error filtering flows: {e}")
            return flows

    def clear_flows(self) -> bool:
        """Clear all flows"""
        try:
            if self.master_instance and self.master_instance.view:
                self.master_instance.view.clear()
                return True
            return False
        except Exception as e:
            logger.error(f"Error clearing flows: {e}")
            return False

    def update_flow(self, flow_obj: flow.Flow) -> bool:
        """Update a flow"""
        try:
            if self.master_instance and self.master_instance.view:
                self.master_instance.view.update([flow_obj])
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating flow: {e}")
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
            logger.error(f"Error deleting flow: {e}")
            return False

    def add_flow(self, flow_obj: flow.Flow) -> bool:
        """Add a flow"""
        try:
            if self.master_instance and self.master_instance.view:
                self.master_instance.view.add([flow_obj])
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding flow: {e}")
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
            logger.error(f"Error resuming flows: {e}")
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
            logger.error(f"Error killing flows: {e}")
            return 0

    def replay_flow(self, flow_obj: flow.Flow) -> bool:
        """Replay a flow"""
        try:
            if self.master_instance and hasattr(self.master_instance, "commands"):
                self.master_instance.commands.call("replay.client", [flow_obj])
                return True
            return False
        except Exception as e:
            logger.error(f"Error replaying flow: {e}")
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

            logger.info(f"Loaded {flows_loaded} flows from dump")
            return True

        except Exception as e:
            logger.error(f"Error loading flows from dump: {e}")
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
            logger.error(f"Error exporting flows to dump: {e}")
            return b""

    async def export_traffic(self, format: str = "json") -> Any:
        """Export captured traffic in specified format"""
        try:
            flows = self.get_flows()

            if format == "json":
                # Export as JSON
                flows_data = []
                for flow_obj in flows:
                    flows_data.append(flow_to_json(flow_obj))
                return flows_data
            elif format == "dump":
                # Export as mitmproxy dump format
                return self.export_flows_to_dump(flows)
            else:
                raise ValueError(f"Unsupported export format: {format}")

        except Exception as e:
            logger.error(f"Error exporting traffic: {e}")
            raise

    async def clear_traffic(self) -> bool:
        """Clear all captured traffic"""
        try:
            return self.clear_flows()
        except Exception as e:
            logger.error(f"Error clearing traffic: {e}")
            return False

    async def handle_message(self, websocket: WebSocket, data: str):
        """Handle WebSocket message"""
        try:
            import json

            message = json.loads(data)

            # Check device_id if it exists in the message
            if "device_id" in message and message["device_id"] != self.device_id:
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "error",
                        "message": f"Device ID mismatch: expected {self.device_id}, got {message['device_id']}",
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
                    # Check su availability before getting state
                    await self._check_su_availability()

                    # Get backend container IP if not set
                    if not self.backend_ip:
                        self.backend_ip = await self._get_backend_ip()

                    state = await self.get_state()
                    # Add su availability information to state
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
                        stdout, stderr = await process.communicate()

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
                                    else f"Reboot error: {stderr.decode()}"
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
            logger.error(f"Error handling message: {e}")
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
            logger.error(f"Error getting options: {e}")
            return {}

    def update_options(self, options_dict: dict) -> bool:
        """Update mitmproxy options"""
        try:
            if self.master_instance:
                self.master_instance.options.update(**options_dict)
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating options: {e}")
            return False

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
            logger.error(f"Error getting state: {e}")
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
            logger.info(f"Proxy port set to {port}")
            return True
        else:
            logger.warning(f"Port {port} is not available")
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
            logger.error(f"Error getting commands: {e}")
            return {}

    def execute_command(self, cmd: str, args: List[str] = None) -> Any:
        """Execute a command"""
        try:
            if self.master_instance and hasattr(self.master_instance, "commands"):
                args = args or []
                return self.master_instance.commands.call_strings(cmd, args)
            return None
        except Exception as e:
            logger.error(f"Error executing command {cmd}: {e}")
            raise

    # Certificate management methods (keep your existing implementation)
    async def generate_certificate(self) -> Optional[str]:
        """Generate mitmproxy certificate"""
        # Keep your existing implementation
        try:
            logger.info("Generating mitmproxy certificate")

            cert_path = os.path.join(self.certs_dir, "mitmproxy-ca-cert.pem")

            if os.path.exists(cert_path):
                logger.info(f"Certificate already exists at {cert_path}")
                return cert_path

            temp_opts = options.Options(confdir=self.data_dir)

            # Create certificate using mitmproxy's certificate authority
            from mitmproxy import certs

            ca = certs.CertStore.from_store(self.data_dir, "mitmproxy", 2048)

            with open(cert_path, "wb") as f:
                f.write(ca.default_ca.to_pem())

            logger.info(f"Certificate generated at {cert_path}")
            return cert_path

        except Exception as e:
            logger.error(f"Error generating certificate: {str(e)}")
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
            logger.debug(f"Port {port} is not available: {e}")
            return False

    def _check_port_sync(self, port: int) -> bool:
        """Synchronous port check"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            # Set flags for port reuse
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            result = sock.bind(("0.0.0.0", port))
            sock.close()
            return True
        except Exception as e:
            logger.debug(f"Port {port} is not available: {e}")
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
            stdout, stderr = await process.communicate()

            if process.returncode == 0 and stdout.strip():
                logger.info(f"Port {port} is being used by:")
                logger.info(stdout.decode().strip())
            else:
                logger.info(f"lsof shows no processes using port {port}")

        except Exception as e:
            logger.warning(f"Error diagnosing port usage: {e}")

    async def _safe_release_port(self):
        """Safely release the proxy port by waiting for natural release"""
        try:
            # Diagnose what's using the port
            await self._diagnose_port_usage(self.proxy_port)

            # Wait for natural port release with multiple attempts
            logger.info(f"Waiting for port {self.proxy_port} to be released naturally")

            # Attempt 1: short wait
            await asyncio.sleep(1)
            if await self._check_port_available(self.proxy_port):
                logger.info(f"Port {self.proxy_port} is now available after short wait")
                return

            # Attempt 2: medium wait
            logger.info(f"Port {self.proxy_port} still in use, waiting longer...")
            await asyncio.sleep(3)
            if await self._check_port_available(self.proxy_port):
                logger.info(
                    f"Port {self.proxy_port} is now available after medium wait"
                )
                return

            # Attempt 3: long wait
            logger.info(f"Port {self.proxy_port} still in use, waiting even longer...")
            await asyncio.sleep(5)
            if await self._check_port_available(self.proxy_port):
                logger.info(f"Port {self.proxy_port} is now available after long wait")
                return

            # If port is still in use, log warning and re-diagnose
            logger.warning(
                f"Port {self.proxy_port} is still in use after all waiting attempts"
            )
            await self._diagnose_port_usage(self.proxy_port)

        except Exception as e:
            logger.warning(f"Error in safe port release: {e}")

    async def _cleanup_all_mitmproxy_processes(self):
        """Clean up all mitmproxy processes - simplified version"""
        try:
            logger.info("Skipping process cleanup - using natural port release")
            # Just wait for natural port release
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Error in cleanup: {e}")

    async def install_certificate(self, websocket: Optional[WebSocket] = None) -> bool:
        """Install certificate on device"""
        try:
            logger.info(f"Installing certificate on device {self.device_id}")

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
                logger.info(f"Certificate hash (subject_hash_old): {cert_hash}")
            else:
                # Fallback to old method
                cert_hash = hashlib.md5(cert_content).hexdigest()[:8]
                logger.warning(
                    f"Failed to get subject_hash_old, using MD5 fallback: {cert_hash}"
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
                logger.error(f"Failed to push certificate: {stderr.decode()}")
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
                        "message": "Certificate copied to device but cannot install to system store without root access",
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
                logger.error(f"su access verification failed: {test_stderr.decode()}")
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
                logger.info(f"Android SDK version: {sdk_version}")

                # Android 14 (API 34) and above use APEX container
                if sdk_version >= 34:
                    logger.info(
                        "Android 14+ detected, certificate installation may require additional steps"
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
                            "message": "Android 14+ detected. System certificate installation may not work due to APEX containers. Consider using Magisk modules.",
                        },
                    )
            except:
                logger.warning(
                    "Could not determine Android version, using default path"
                )

            # Check existing certificates in system
            list_certs_cmd = f"adb -s {self.device_id} shell su 0 ls -la /system/etc/security/cacerts/ | head -10"
            list_process = await asyncio.create_subprocess_shell(
                list_certs_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            list_stdout, list_stderr = await list_process.communicate()

            if list_process.returncode == 0:
                existing_certs = list_stdout.decode().strip()
                logger.info(f"Existing system certificates: {existing_certs}")
            else:
                logger.warning(
                    f"Failed to list existing certificates: {list_stderr.decode()}"
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
            logger.info(f"Installing certificate:")
            logger.info(f"  - Device cert path: {device_cert_path}")
            logger.info(f"  - System cert path: {system_cert_path}")
            logger.info(f"  - Certificate hash: {cert_hash}")

            install_commands = [
                f"adb -s {self.device_id} shell su 0 cp {device_cert_path} {system_cert_path}",
                f"adb -s {self.device_id} shell su 0 chmod 644 {system_cert_path}",
                f"adb -s {self.device_id} shell su 0 chown root:root {system_cert_path}",
            ]

            success_count = 0
            for i, cmd in enumerate(install_commands):
                logger.info(f"Executing install command {i+1}/3: {cmd}")
                process = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()

                if process.returncode == 0:
                    success_count += 1
                    logger.info(f"Command {i+1} succeeded: {stdout.decode().strip()}")
                else:
                    logger.error(f"Command {i+1} failed: {stderr.decode()}")

            logger.info(f"Install commands: {success_count}/3 successful")

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
                logger.info(f"Certificate verification: {file_info}")

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
                        logger.error(f"Original length: {len(original_cert)}")
                        logger.error(f"Installed length: {len(installed_cert)}")
                        logger.error(
                            f"First 100 chars of installed: {installed_cert[:100]}"
                        )
                        self.cert_installed = False
                else:
                    logger.error(
                        f"Failed to read installed certificate: {compare_stderr.decode()}"
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
                            f"Certificate file stats: {stat_stdout.decode().strip()}"
                        )

                if self.cert_installed:
                    logger.info(
                        f"✅ Certificate successfully installed and verified at {system_cert_path}"
                    )

            else:
                logger.error(
                    f"❌ Certificate verification failed: {verify_stderr.decode()}"
                )
                self.cert_installed = False

            # Suggest reboot to activate certificate only if installation was successful
            if self.cert_installed:
                await self.send_response(
                    websocket,
                    {
                        "type": "mitmproxy",
                        "action": "certificate_installed_reboot_needed",
                        "message": "Certificate installed successfully. Reboot is recommended to activate it.",
                        "reboot_available": True,
                    },
                )
                return True
            else:
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
            logger.error(f"Error installing certificate: {str(e)}")
            return False

    async def send_response(self, websocket: Optional[WebSocket], response_data: dict):
        """Send response through WebSocket"""
        try:
            if websocket is not None:
                await websocket.send_text(json.dumps(response_data))
            else:
                # For HTTP endpoints, just log the response
                logger.info(f"HTTP endpoint response: {response_data}")
        except Exception as e:
            logger.error(f"Error sending response: {e}")

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
                logger.error(f"HTTP endpoint error: {message}")
        except Exception as e:
            logger.error(f"Error sending error response: {e}")

    async def configure_device_proxy(
        self, websocket: Optional[WebSocket] = None
    ) -> bool:
        """Configure proxy on device"""
        try:
            logger.info(f"Configuring proxy on device {self.device_id}")

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
                cmd = f"adb -s {self.device_id} shell su 0 settings put global http_proxy {proxy_setting}"
            else:
                # Try to configure without su
                cmd = f"adb -s {self.device_id} shell settings put global http_proxy {proxy_setting}"

            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Proxy configured successfully: {proxy_setting}")

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
                logger.info(f"Current proxy setting: {current_proxy}")

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
            else:
                logger.error(f"Failed to configure proxy: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error configuring proxy: {str(e)}")
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
                            f"Found emulator {emulator['name']} for device {self.device_id}"
                        )
                        return emulator["name"]

            logger.info(f"Device {self.device_id} is not a Docker emulator")
            return None

        except Exception as e:
            logger.warning(f"Could not determine emulator name: {str(e)}")
            return None

    async def _initialize_backend_ip(self) -> None:
        """Initialize backend container IP address"""
        try:
            self.backend_ip = await self._get_backend_ip()
            logger.info(f"Backend IP initialized: {self.backend_ip}")
        except Exception as e:
            logger.error(f"Error initializing backend IP: {e}")
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
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Get first IP address
                ips = stdout.decode().strip().split()
                if ips:
                    backend_ip = ips[0]
                    logger.info(f"Backend container IP: {backend_ip}")
                    return backend_ip

            # Method 2: Read IP from /proc/net/route (default routing)
            try:
                with open("/proc/net/route", "r") as f:
                    for line in f:
                        fields = line.split()
                        if (
                            len(fields) >= 8 and fields[1] == "00000000"
                        ):  # Default route
                            # Get interface IP
                            interface = fields[0]
                            process = await asyncio.create_subprocess_shell(
                                f"ip addr show {interface} | grep 'inet ' | head -1 | awk '{{print $2}}' | cut -d/ -f1",
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            stdout, _ = await process.communicate()
                            if process.returncode == 0:
                                ip = stdout.decode().strip()
                                if ip and not ip.startswith("127."):
                                    logger.info(
                                        f"Backend container IP from route: {ip}"
                                    )
                                    return ip
                            break
            except Exception:
                pass

            # Fallback to old value
            logger.warning("Could not determine backend IP, using fallback")
            return None

        except Exception as e:
            logger.error(f"Error getting backend IP: {str(e)}")
            return None  # Fallback

    async def _get_device_ip(self) -> None:
        """Get device IP address"""
        try:
            # Try to get IP from ADB
            cmd = f"adb -s {self.device_id} shell ip route get 1.1.1.1"
            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                output = stdout.decode().strip()
                # Parse output to get IP
                parts = output.split()
                if "src" in parts:
                    src_index = parts.index("src")
                    if src_index + 1 < len(parts):
                        self.device_ip = parts[src_index + 1]
                        logger.info(f"Device IP: {self.device_ip}")
                        return

            # Alternative method
            cmd = f"adb -s {self.device_id} shell ifconfig | grep 'inet addr'"
            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                # Look for first non-localhost IP
                lines = stdout.decode().split("\n")
                for line in lines:
                    if "inet addr:" in line and "127.0.0.1" not in line:
                        ip_part = line.split("inet addr:")[1].split()[0]
                        self.device_ip = ip_part
                        logger.info(f"Device IP (alternative): {self.device_ip}")
                        return

            logger.warning("Could not determine device IP")

        except Exception as e:
            logger.error(f"Error getting device IP: {str(e)}")

    async def _check_su_availability(self) -> None:
        """Check su availability on device"""
        try:
            cmd = f"adb -s {self.device_id} shell su 0 id"
            process = await asyncio.create_subprocess_shell(
                cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0 and "root" in stdout.decode():
                self.su_available = True
                logger.info("su is available on device")
            else:
                self.su_available = False
                logger.info("su is not available on device")

        except Exception as e:
            logger.error(f"Error checking su availability: {str(e)}")
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
                check_cmd = f"adb -s {self.device_id} shell su 0 test -f {system_cert_path} && echo 'exists'"
                check_process = await asyncio.create_subprocess_shell(
                    check_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                check_stdout, check_stderr = await check_process.communicate()

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
                                f"✅ Mitmproxy certificate verified at {system_cert_path}"
                            )
                        else:
                            logger.warning(
                                f"❌ Certificate content mismatch at {system_cert_path}"
                            )
                    else:
                        logger.warning(
                            f"❌ Cannot read certificate at {system_cert_path}"
                        )
                else:
                    logger.info(f"❌ Certificate not found at {system_cert_path}")
            else:
                os.unlink(temp_cert_file)
                logger.warning(f"Failed to get certificate hash: {stderr.decode()}")

        except Exception as e:
            logger.error(f"Error checking certificate status: {str(e)}")
            self.cert_installed = False


_mitmproxy_managers: Dict[str, MitmproxyManager] = {}
_manager_lock = asyncio.Lock()


async def get_mitmproxy_manager(device_id: str) -> MitmproxyManager:
    """Get MitmproxyManager instance for device"""
    async with _manager_lock:
        if device_id not in _mitmproxy_managers:
            logger.info(f"Creating new mitmproxy manager for device {device_id}")
            _mitmproxy_managers[device_id] = MitmproxyManager(device_id)
        else:
            logger.info(f"Reusing existing mitmproxy manager for device {device_id}")
        return _mitmproxy_managers[device_id]


async def cleanup_mitmproxy_manager(device_id: str):
    """Clean up MitmproxyManager instance for device"""
    async with _manager_lock:
        if device_id in _mitmproxy_managers:
            manager = _mitmproxy_managers[device_id]
            logger.info(f"Cleaning up mitmproxy manager for device {device_id}")
            try:
                await manager.stop()
            except Exception as e:
                logger.error(f"Error stopping manager during cleanup: {e}")
            del _mitmproxy_managers[device_id]
            logger.info(f"Cleaned up mitmproxy manager for device {device_id}")
        else:
            logger.info(
                f"No mitmproxy manager found for device {device_id} during cleanup"
            )
