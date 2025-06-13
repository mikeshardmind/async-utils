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

import asyncio
import concurrent.futures as cf
import contextvars

# PYUPDATE: 3.14 release + 3.14 minimum: reaudit
# heapq methods are not threadsafe pre 3.14
# see: GH: cpython 135036
import heapq
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager

from . import _typings as t

__all__ = ("PrioritySemaphore", "priority_context")


_priority: contextvars.ContextVar[int] = contextvars.ContextVar("_priority", default=0)


class _PriorityWaiter:
    __slots__ = ("future", "ord")

    def __init__(self, priority: int, ts: float, future: cf.Future[None], /) -> None:
        self.future: cf.Future[None] = future
        self.ord: tuple[int, float] = (priority, ts)

    def cancelled(self) -> bool:
        return self.future.cancelled()

    def done(self) -> bool:
        return self.future.done()

    def set_result(self, val: None) -> None:
        self.future.set_result(val)

    def __await__(self) -> Generator[t.Any, t.Any, None]:
        f = asyncio.wrap_future(self.future)
        return (yield from f.__await__())

    def __lt__(self: t.Self, other: object) -> bool:
        if not isinstance(other, _PriorityWaiter):
            return NotImplemented
        return self.ord < other.ord

    __final__ = True

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)


@contextmanager
def priority_context(priority: int, /) -> Generator[None, None, None]:
    """Set the priority for all PrioritySemaphore use in this context.

    Parameters
    ----------
    priority: int
        The priority to use. Lower values are of a higher priority.
    """
    token = _priority.set(priority)
    try:
        yield None
    finally:
        _priority.reset(token)


class PrioritySemaphore:
    """A Semaphore with priority-based aquisition ordering.

    Provides a semaphore with similar semantics as asyncio.Semaphore,
    but using an underlying priority. Priority is shared within a context
    manager's logical scope, but the context is safely reentrant.

    This can be safely shared across multiple asyncio event loops in
    multiple threads.

    Lower priority values are a higher logical priority

    Parameters
    ----------
    value: int
        The initial value of the internal counter.
        The number of things that can concurrently acquire it.

    Examples
    --------
    >>> sem = PrioritySemaphore(1)
    >>> with priority_ctx(10):
            async with sem:
                ...

    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, value: int = 1) -> None:
        if value < 0:
            msg = "Semaphore initial value must be >= 0"
            raise ValueError(msg)
        self._waiters: list[_PriorityWaiter] | None = None
        self._value: int = value
        # PYUPDATE: 3.14 minimum heapq safety
        self._internal_lock: threading.RLock = threading.RLock()

    def __locked(self) -> bool:
        # Must do a comparison based on priority then FIFO
        # in the case of existing waiters
        # not guaranteed to be immediately available
        with self._internal_lock:
            return self._value == 0 or (
                any(not w.cancelled() for w in (self._waiters or ()))
            )

    async def __aenter__(self) -> None:
        prio = _priority.get()
        await self.__acquire(prio)

    async def __aexit__(self, *dont_care: object) -> None:
        self.__release()

    async def __acquire(self, priority: int, /) -> bool:
        if not self.__locked():
            self._value -= 1
            return True

        if self._waiters is None:
            self._waiters = []

        fut: cf.Future[None] = cf.Future()
        now = time.monotonic()
        waiter = _PriorityWaiter(priority, now, fut)

        with self._internal_lock:
            heapq.heappush(self._waiters, waiter)

        try:
            await waiter
            # unlike a normal semaphore, we don't remove ourselves
            # we need to maintain the heap invariants
        except asyncio.CancelledError:
            if fut.done() and not fut.cancelled():
                self._value += 1
            raise

        finally:
            self._maybe_wake()
        return True

    def _maybe_wake(self) -> None:
        with self._internal_lock:
            while self._value > 0 and self._waiters:
                next_waiter = heapq.heappop(self._waiters)

                if not (next_waiter.done() or next_waiter.cancelled()):
                    self._value -= 1
                    next_waiter.set_result(None)

            while self._waiters:
                # cleanup maintaining heap invariant
                # This will only fully empty the heap when
                # all things remaining in the heap after waking tasks in
                # above section are all done.
                next_waiter = heapq.heappop(self._waiters)
                if not (next_waiter.done() or next_waiter.cancelled()):
                    heapq.heappush(self._waiters, next_waiter)
                    break

    def __release(self) -> None:
        self._value += 1
        self._maybe_wake()
