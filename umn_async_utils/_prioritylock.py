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

# The code here stands heavily upon the shoulders of work done in CPython
# the lock here is a reimplementation of CPython's asyncio.Lock retaining most of the same interface and intent of use.
# Locking mechanisms themselves are well studied and essential to many methods of multi-tasking work, but the implementation here
# works under several assumptions about the environment, namely the specifics of python and asyncio.
# It would be impossible for me to create this without in some way being influenced by the original and to the
# extent which that is the case, this may be considered derivative.

# You may find a full copy of the license of CPython included in the project root as well as online at
# <https://github.com/python/cpython/blob/main/LICENSE>
# and the specific Lock which is being implemented with a modification in behavior online at
# <

from __future__ import annotations

import asyncio
import threading
from contextlib import contextmanager
from contextvars import ContextVar, Token
from functools import total_ordering
from heapq import heappush
from itertools import count
from types import TracebackType
from typing import Any, Literal

# fun of working with futures and thread specific event loops
_thread_lock = threading.Lock()

# This serves as a tie-break mechanism for stable ordering of heaps, as well as FIFO within same priority.
_global_counter = count()
_priority = ContextVar("_priority", default=1)


@total_ordering
class WaitEntry:
    __slots__ = ("priority", "count", "future")

    def __init__(self, future: asyncio.Future[Literal[True]], /):
        self.priority = _priority.get()
        self.count = next(_global_counter)
        self.future: asyncio.Future[Literal[True]] = future

    def __lt__(self, other: Any):
        if not isinstance(other, WaitEntry):
            return NotImplemented
        return (self.priority, self.count) < (other.priority, other.count)


@contextmanager
def priority(p: int, /):
    reset_token: Token[int] | None = None
    try:
        reset_token = _priority.set(p)
        yield None
    finally:
        if reset_token is not None:
            _priority.reset(reset_token)


class PriorityLock:
    """
    This implements the same interface as asyncio.Lock
    Many of the design choices will appear similar the same as a result.

    This is not a fair lock by design, and is intended to have things which are more important take precedence.

    This lock assumes that there will be instances where it will be acquired without contention at least periodically
    """

    def __init__(self):
        self._waiters: list[WaitEntry] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._locked: bool = False

    # this type is a slight lie, but when only called from async functions as below, it's correct.
    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio._get_running_loop()  # type: ignore  # private usage of function documented for low level use

        if self._loop is None:
            # check above is cheap, but we need to re-check under lock
            with _thread_lock:
                if self._loop is None:
                    self._loop = loop
        if self._loop is not loop:
            raise RuntimeError(
                "Something something don't reuse locks between event loops."
            )
        return loop

    async def __aenter__(self):
        await self.acquire()
        return None

    async def __aexit__(
        self, exc_type: type[Exception], exc: Exception, tb: TracebackType
    ):
        self.release()

    async def acquire(self):

        if not self._locked and all(
            wait_entry.future.done() for wait_entry in self._waiters
        ):
            # Under the assumption that the lock is not contested 100% of the time
            # this is better than removal + re-heapifying each time
            # the lock is aquired in the alternative case.
            self._waiters.clear()
            self._locked = True
            return True

        loop = self._get_event_loop()

        fut = loop.create_future()
        waiter = WaitEntry(fut)
        heappush(self._waiters, waiter)

        try:
            await fut
        except asyncio.CancelledError:
            if not self._locked:
                self._wake_up_first()
            raise

        self._locked = True
        return True

    def release(self):

        if self._locked:
            self._locked = False
            self._wake_up_first()
        else:
            raise RuntimeError("Lock is not acquired.")

    def _wake_up_first(self):
        if not self._waiters:
            return
        try:
            # the 0th element of a heap is always also the heap minimum
            # the same does not hold for all indices
            wait_entry = next(iter(self._waiters))
        except StopIteration:
            return

        if not wait_entry.future.done():
            wait_entry.future.set_result(True)
