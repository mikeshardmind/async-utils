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

import select
import signal
import socket
import sys
from collections.abc import Callable
from types import FrameType
from typing import Any

type SignalCallback = Callable[[signal.Signals], Any]
type StartStopCall = Callable[[], Any]
type _HANDLER = Callable[[int, FrameType | None], Any] | int | signal.Handlers | None

__all__ = ["SignalService"]

possible = "SIGINT", "SIGTERM", "SIGBREAK", "SIGHUP"
actual = tuple(e for name, e in signal.Signals.__members__.items() if name in possible)


class SignalService:
    """Meant for graceful signal handling where the main thread is only used for signal handling.
    This should be paired with event loops being run in threads."""

    def __init__(self, *, startup: list[StartStopCall], signal_cbs: list[SignalCallback], joins: list[StartStopCall]) -> None:
        self._startup: list[StartStopCall] = startup
        self._cbs: list[SignalCallback] = signal_cbs
        self._joins: list[StartStopCall] = joins

    def run(self):
        ss, cs = socket.socketpair()
        ss.setblocking(False)
        cs.setblocking(False)
        signal.set_wakeup_fd(cs.fileno())

        original_handlers: list[_HANDLER] = []

        for sig in actual:
            original_handlers.append(signal.getsignal(sig))
            signal.signal(sig, lambda s, f: None)
            if sys.platform != "win32":
                signal.siginterrupt(sig, False)

        for task_start in self._startup:
            task_start()

        select.select([ss], [], [])
        data, *_ = ss.recv(4096)

        for cb in self._cbs:
            cb(signal.Signals(data))

        for join in self._joins:
            join()

        for sig, original in zip(actual, original_handlers):
            signal.signal(sig, original)
