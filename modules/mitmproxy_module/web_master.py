import logging
from typing import List, Callable

from mitmproxy import master, options, log, optmanager
from mitmproxy import addons
from mitmproxy.addons import errorcheck
from mitmproxy.addons import eventstore
from mitmproxy.addons import intercept
from mitmproxy.addons import readfile
from mitmproxy.addons import view


logger = logging.getLogger(__name__)


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
