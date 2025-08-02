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

# This is one of the few things that should unreservedly be reimplemented natively.
# Atomic ops allow the removal of the internal locking.

# We can also do a little bit better prior to making it native by only locking
# if we observe multiple threads. The gain for this is minor, but not insignificant.

# This particular lock implementation optimizes for the uncontested lock case.
# This is the most important optimization for well-designed parallel code
# with fine-grained lock use. It's also barging, which is known to be better
# than FIFO in the case of highly contested locks.


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

    async def __aenter__(self) -> None:
        with self._internal_lock:
            if not self._lockv:
                self._lockv = True
                return

        fut: cf.Future[None] = cf.Future()

        self._waiters.append(fut)

        try:
            await asyncio.wrap_future(fut)
        except asyncio.CancelledError:
            with self._internal_lock:
                if not self._lockv:
                    self._maybe_wake()
            raise

        with self._internal_lock:
            self._lockv = True

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
        with self._internal_lock:
            self._lockv = False
            self._maybe_wake()
        return False
