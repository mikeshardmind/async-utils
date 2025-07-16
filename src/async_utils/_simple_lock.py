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

import asyncio
import concurrent.futures as cf
import threading
from collections import deque

from . import _typings as t

# TODO: pick what public namespace to re-export this from.


class AsyncLock:
    """An async lock that doesn't bind to an event loop."""

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self) -> None:
        self._waiters: deque[cf.Future[None]] = deque()
        self._internal_lock: threading.RLock = threading.RLock()
        self._locked: bool = False

    async def __aenter__(self, /) -> None:
        with self._internal_lock:
            if not self._locked and (all(w.cancelled() for w in self._waiters)):
                self._locked = True
                return

        fut: cf.Future[None] = cf.Future()

        with self._internal_lock:
            self._waiters.append(fut)

        try:
            await asyncio.wrap_future(fut)
        except (asyncio.CancelledError, cf.CancelledError):
            with self._internal_lock:
                if self._locked:
                    self._maybe_wake()
        finally:
            self._waiters.remove(fut)

    async def __aexit__(self, *_dont_care: object) -> t.Literal[False]:
        with self._internal_lock:
            if self._locked:
                self._locked = False
                self._maybe_wake()

        return False

    def _maybe_wake(self) -> None:
        with self._internal_lock:
            if self._waiters:
                try:
                    fut = next(iter(self._waiters))
                except StopIteration:
                    return
                if not fut.done():
                    fut.set_result(None)
