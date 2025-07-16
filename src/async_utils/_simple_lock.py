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
        self._lockv: bool = False
        self._internal_lock: threading.RLock = threading.RLock()

    def __locked(self) -> bool:
        with self._internal_lock:
            return self._lockv or (any(not w.cancelled() for w in (self._waiters)))

    async def __aenter__(self) -> None:
        await asyncio.sleep(0)  # This yield is non-optional.

        with self._internal_lock:
            if not self.__locked():
                self._lockv = True
                return

        fut: cf.Future[None] = cf.Future()

        with self._internal_lock:
            self._waiters.append(fut)

        try:
            await asyncio.wrap_future(fut)
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self._lockv = False
            raise

        finally:
            self._maybe_wake()
        return

    def _maybe_wake(self) -> None:
        with self._internal_lock:
            while (not self._lockv) and self._waiters:
                next_waiter = self._waiters.popleft()

                if not (next_waiter.done() or next_waiter.cancelled()):
                    self._lockv = True
                    next_waiter.set_result(None)

            while self._waiters:
                next_waiter = self._waiters.popleft()
                if not (next_waiter.done() or next_waiter.cancelled()):
                    self._waiters.appendleft(next_waiter)
                    break

    async def __aexit__(self, *dont_care: object) -> t.Literal[False]:
        await asyncio.sleep(0)  # this yield is not optional
        with self._internal_lock:
            self._lockv = False
            self._maybe_wake()
        return False
