#   Copyright 2020-present Michael Hall
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from __future__ import annotations

import enum
import select
import signal
import socket
import sys
from collections.abc import Callable
from types import FrameType
from typing import Any, Literal

type SignalCallback = Callable[[signal.Signals | SpecialExit], Any]
type StartStopCall = Callable[[], Any]
type _HANDLER = (
    Callable[[int, FrameType | None], Any] | int | signal.Handlers | None
)
type SignalTuple = tuple[
    Literal["SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"], ...
]

__all__ = ["SignalService", "SpecialExit"]


default_handled = "SIGINT", "SIGTERM", "SIGBREAK"


class SpecialExit(enum.IntEnum):
    """A Special enum wrapping normal exit codes."""

    EXIT = 252


class SignalService[T: SignalTuple]:
    """Helper for signal handling.

    Meant for graceful signal handling where the main thread is only used
    for signal handling.
    This should be paired with event loops being run in threads.
    """

    def __init__(self, signals: T = default_handled, /) -> None:
        self._startup: list[StartStopCall] = []
        self._cbs: list[SignalCallback] = []
        self._joins: list[StartStopCall] = []
        self.ss, self.cs = socket.socketpair()
        self.ss.setblocking(False)
        self.cs.setblocking(False)
        self._signals = tuple(
            e
            for name, e in signal.Signals.__members__.items()
            if name in signals
        )

    def get_send_socket(self) -> socket.socket:
        """Get the send socket.

        Returns
        -------
        socket.socket
            A non-blocking socket that can be used to send shutdown signals
            without recieving them directly from the host operating system.

            This is typically useful to signal shutdown triggered from within
            the application to other parts of the application that need to
            then handle graceful shutdown.
        """
        return self.cs

    def add_startup(self, job: StartStopCall) -> None:
        """Add a function which will be called on startup."""
        self._startup.append(job)

    def add_signal_cb(self, cb: SignalCallback) -> None:
        """Add a callback function which will recieve signals."""
        self._cbs.append(cb)

    def add_join(self, join: StartStopCall) -> None:
        """Addd a method which should be called before exiting.

        This is primarily intended for things like Thread.join, Queue.join, etc.
        """
        self._joins.append(join)

    def run(self) -> None:
        """Run in order the methods which were addedd.

        This entails first intercepting signal handling,
        then starting added tasks in order.

        Upon recieving a signal, each signal callback is called in the
        order they were added.

        then, in order added, each join is called.

        User provided order is used for each. It is the user's responsibility
        to ensure this cannot deadlock.

        After all user provide functions have been called, the original signal
        handlers are restored.
        """
        signal.set_wakeup_fd(self.cs.fileno())

        original_handlers: list[_HANDLER] = []

        try:
            for sig in self._signals:
                original_handlers.append(signal.getsignal(sig))
                signal.signal(sig, lambda s, f: None)
                if sys.platform != "win32":
                    signal.siginterrupt(sig, False)

            for task_start in self._startup:
                task_start()

            select.select([self.ss], [], [])
            data, *_ = self.ss.recv(4096)
            sig = signal.Signals(data) if data != 252 else SpecialExit.EXIT

            for cb in self._cbs:
                cb(sig)

            for join in self._joins:
                join()

        finally:
            for sig, original in zip(
                self._signals, original_handlers, strict=False
            ):
                signal.signal(sig, original)
