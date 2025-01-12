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

# This used to include CPython code, some minor performance losses have been
# taken to not tightly include upstream code
"""Building blocks used to create thread-safe multi-event loop async things."""

from __future__ import annotations

import asyncio
import concurrent.futures as cf
import threading
from collections import deque
from collections.abc import Callable, Generator

from . import _typings as t


class _NMWaiter:
    # This is for internal use only, tested on both 3.12 and 3.13
    # This will be tested for 3.14 prior to 3.14's release.
    __slots__ = ("_future", "_val")

    def __init__(self, val: int = 1, /) -> None:
        # This is why this is for internal use only
        self._future: cf.Future[None] = cf.Future()
        self._val = val

    def __lt__(self, other: object) -> bool:
        if isinstance(other, _NMWaiter):
            return self._val < other._val
        return NotImplemented

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __await__(self) -> Generator[t.Any, None, None]:
        return asyncio.wrap_future(self._future).__await__()

    def wake(self) -> None:
        if not self._future.done():
            try:
                # This is why this is for internal use only
                self._future.set_result(None)
            except cf.InvalidStateError:
                # Race condition possible with multiple attempts to wake
                # Racing in some cases is less expensive than locking in all
                pass

    def cancelled(self):
        return self._future.cancelled()

    def done(self):
        return self._future.done()

    def add_done_callback(self, cb: Callable[[cf.Future[None]], None]) -> None:
        self._future.add_done_callback(cb)


class _WrappedRLock:
    __slots__ = ("_lock",)

    def __init__(self, lock: threading.RLock) -> None:
        self._lock = lock

    async def __aenter__(self) -> None:
        acquired = False
        while not acquired:
            acquired = self._lock.acquire(blocking=False)
            await asyncio.sleep(0)

    async def __aexit__(self, *dont_care: object) -> None:
        self._lock.release()


class NMSemaphore:
    __final__ = True
    __slots__ = ("_lock", "_value", "_waiters")

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    def __init__(self, value: int = 1, /) -> None:
        self._waiters: deque[_NMWaiter] = deque()
        self._lock = _WrappedRLock(threading.RLock())
        self._value: int = value

    def __repr__(self) -> str:
        res = super().__repr__()
        extra = "locked" if self.__locked() else f"unlocked, value:{self._value}"
        if self._waiters:
            extra = f"{extra}, waiters:{len(self._waiters)}"
        return f"<{res[1:-1]} [{extra}]>"

    def __locked(self) -> bool:
        return self._value == 0 or (any(not w.cancelled() for w in (self._waiters or ())))

    async def __aexit__(self, *dont_care: object) -> None:
        async with self._lock:
            self._value += 1
        await self._async_maybe_wake()

    async def __aenter__(self) -> None:
        async with self._lock:
            if not self.__locked():
                self._value -= 1
                return

            waiter = _NMWaiter()
            self._waiters.append(waiter)

        try:
            await waiter
        except asyncio.CancelledError:
            if waiter.done() and not waiter.cancelled():
                self._value += 1
            raise

        finally:
            await self._async_maybe_wake()

    async def _async_maybe_wake(self) -> None:
        async with self._lock:
            while self._value > 0 and self._waiters:
                next_waiter = self._waiters.popleft()

                if not (next_waiter.done() or next_waiter.cancelled()):
                    self._value -= 1
                    next_waiter.wake()

            while self._waiters:
                next_waiter = self._waiters.popleft()
                if not (next_waiter.done() or next_waiter.cancelled()):
                    self._waiters.appendleft(next_waiter)
                    break
