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
import heapq

from collections.abc import Callable
from typing import Any, NamedTuple
import threading
import contextvars
from contextlib import contextmanager

__all__ = ["priority_context", "PrioritySemaphore"]

_global_lock = threading.Lock()

_priority: contextvars.ContextVar[int] = contextvars.ContextVar("_priority", default=0)

class PriorityWaiter(NamedTuple):
    priority: int
    ts: float
    future: asyncio.Future[None]

    @property
    def cancelled(self) -> Callable[[], bool]:
        return self.future.cancelled

    @property
    def done(self) -> Callable[[], bool]:
        return self.future.done

    def __await__(self):
        return self.future.__await__()

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, PriorityWaiter):
            return NotImplemented
        return (0 - self.priority, self.ts) < (0 - other.priority, other.ts)


@contextmanager
def priority_context(priority: int):
    token = _priority.set(priority)
    try:
        yield None
    finally:
        _priority.reset(token)


class PrioritySemaphore:
    """
    Provides a semaphore with similar semantics as asyncio.Semaphore,
    but using an underlying priority.
    Higher priority matches higher values for priority (Not lower)

    context manager use:

    sem = PrioritySemaphore(1)

    with priority_ctx(10):
        async with sem:
            ...
    """
    _loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self):
        loop = asyncio.get_running_loop()

        if self._loop is None:
            with _global_lock:
                if self._loop is None:
                    self._loop = loop
        if loop is not self._loop:
            raise RuntimeError(f"{self!r} is bound to a different event loop")
        return loop

    def __init__(self, value: int = 1):
        if value < 0:
            raise ValueError("Semaphore initial value must be >= 0")
        self._waiters: list[PriorityWaiter] | None = None
        self._value: int = value

    def __repr__(self):
        res = super().__repr__()
        extra = "locked" if self.locked() else f"unlocked, value:{self._value}"
        if self._waiters:
            extra = f'{extra}, waiters:{len(self._waiters)}'
        return f"<{res[1:-1]} [{extra}]>"

    def locked(self) -> bool:
        # Must do a comparison based on priority then FIFO
        # in the case of existing waiters, not guaranteed to be immediately available
        return self._value == 0 or (
            any(not w.cancelled() for w in (self._waiters or ())))

    async def __aenter__(self):
        prio = _priority.get()
        await self.acquire(prio)
        return None

    async def __aexit__(self, *dont_care: Any):
        self.release()

    async def acquire(self, priority: int) -> bool:
        if not self.locked():
            self._value -= 1
            return True

        if self._waiters is None:
            self._waiters = []

        loop = self._get_loop()

        fut = loop.create_future()
        now = loop.time()
        waiter = PriorityWaiter(priority, now, fut)

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

    def _maybe_wake(self):
        while self._value > 0 and self._waiters:
            next_waiter = heapq.heappop(self._waiters)

            if not (next_waiter.done() or next_waiter.cancelled()):
                self._value -= 1
                next_waiter.future.set_result(None)

        while self._waiters:
            # cleanup maintaining heap invariant
            # This will only fully empty the heap when
            # all things remaining in the heap after waking tasks in
            # above section are all done.
            next_waiter = heapq.heappop(self._waiters)
            if not (next_waiter.done() or next_waiter.cancelled()):
                heapq.heappush(self._waiters, next_waiter)
                break

    def release(self):
        self._value += 1
        self._maybe_wake()