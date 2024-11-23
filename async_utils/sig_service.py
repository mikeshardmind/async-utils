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
from typing import Any

type SignalCallback = Callable[[signal.Signals | SpecialExit], Any]
type StartStopCall = Callable[[], Any]
type _HANDLER = (
    Callable[[int, FrameType | None], Any] | int | signal.Handlers | None
)

__all__ = ["SignalService", "SpecialExit"]

possible = "SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"
actual = tuple(
    e for name, e in signal.Signals.__members__.items() if name in possible
)


class SpecialExit(enum.IntEnum):
    EXIT = 252


class SignalService:
    """Helper for signal handling.

    Meant for graceful signal handling where the main thread is only used
    for signal handling.
    This should be paired with event loops being run in threads.
    """

    def __init__(
        self,
    ) -> None:
        self._startup: list[StartStopCall] = []
        self._cbs: list[SignalCallback] = []
        self._joins: list[StartStopCall] = []
        self.ss, self.cs = socket.socketpair()
        self.ss.setblocking(False)
        self.cs.setblocking(False)

    def get_send_socket(self) -> socket.socket:
        return self.cs

    def add_startup(self, job: StartStopCall) -> None:
        self._startup.append(job)

    def add_signal_cb(self, cb: SignalCallback) -> None:
        self._cbs.append(cb)

    def add_join(self, join: StartStopCall) -> None:
        self._joins.append(join)

    def run(self) -> None:
        signal.set_wakeup_fd(self.cs.fileno())

        original_handlers: list[_HANDLER] = []

        for sig in actual:
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

        for sig, original in zip(actual, original_handlers, strict=True):
            signal.signal(sig, original)
