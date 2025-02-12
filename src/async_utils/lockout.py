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
import time
from collections import deque

from . import _typings as t

__all__ = ("FIFOLockout", "Lockout")


class Lockout:
    """Lock out an async resource for an amount of time.

    Resources may be locked out multiple times.

    Only prevents new acquires and does not cancel ongoing scopes that
    have already acquired access.

    Does not guarantee FIFO acquisition.

    When paired with locks, semaphores, or ratelimiters, this should
    be the last synchonization acquired and should be acquired immediately.

    Example use could look similar to:

    >>> ratelimiter = Ratelimiter(5, 1, 1)
    >>> lockout = Lockout()
    >>> async def request_handler(route, parameters):
            async with ratelimiter, lockout:
                response = await some_request(route, **parameters)
                if response.code == 429:
                    if reset := response.headers.get('X-Ratelimit-Reset-After')
                        lockout.lock_for(reset)

    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __repr__(self) -> str:
        res = super().__repr__()
        x = f"locked, timestamps={self._lockouts:!r}" if self._lockouts else "unlocked"
        return f"<{res[1:-1]} [{x}]>"

    def __init__(self) -> None:
        self._lockouts: list[float] = []

    def lockout_for(self, seconds: float, /) -> None:
        """Lock a resource for an amount of time."""
        heapq.heappush(self._lockouts, time.monotonic() + seconds)

    async def __aenter__(self) -> None:
        while self._lockouts:
            now = time.monotonic()
            # There must not be an async context switch between here
            # and replacing the lockout when lockout is in the future
            ts = heapq.heappop(self._lockouts)
            if (sleep_for := ts - now) > 0:
                heapq.heappush(self._lockouts, ts)
                await asyncio.sleep(sleep_for)

    async def __aexit__(self, *_dont_care: object) -> None:
        pass


class FIFOLockout:
    """A FIFO preserving version of Lockout.

    This has slightly more
    overhead than the base Lockout class, which is not guaranteed to
    preserve FIFO, though happens to in the case of not being locked.

    Resources may be locked out multiple times.

    Only prevents new acquires and does not cancel ongoing scopes that
    have already acquired access.

    When paired with locks, semaphores, or ratelimiters, this should
    be the last synchonization acquired and should be acquired immediately.

    Example use could look similar to:

    >>> ratelimiter = Ratelimiter(5, 1, 1)
    >>> lockout = FIFOLockout()
    >>> async def request_handler(route, parameters):
            async with ratelimiter, lockout:
                response = await some_request(route, **parameters)
                if response.code == 429:
                    if reset_after := response.headers.get('X-Ratelimit-Reset-After')
                        lockout.lock_for(reset_after)
    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self) -> None:
        self._lockouts: set[asyncio.Task[None]] = set()
        self._waiters: deque[asyncio.Future[None]] = deque()
        self._loop: asyncio.AbstractEventLoop | None = None

    def __repr__(self) -> str:
        res = super().__repr__()
        x = f"locked, timestamps={self._lockouts:!r}" if self._lockouts else "unlocked"
        return f"<{res[1:-1]} [{x}]>"

    def lockout_for(self, seconds: float, /) -> None:
        """Lock a resource for an amount of time."""
        if (loop := self._loop) is None:
            loop = self._loop = asyncio.get_running_loop()
        task = loop.create_task(asyncio.sleep(seconds, None))
        self._lockouts.add(task)
        task.add_done_callback(self._lockouts.discard)

    async def __aenter__(self) -> None:
        if (loop := self._loop) is None:
            loop = self._loop = asyncio.get_running_loop()
        if not self._lockouts and all(f.cancelled() for f in self._waiters):
            return

        fut: asyncio.Future[None] = loop.create_future()
        self._waiters.append(fut)

        while self._lockouts:
            await asyncio.gather(*self._lockouts)

        try:
            try:
                await fut
            finally:
                self._waiters.remove(fut)
        except asyncio.CancelledError:
            if not self._lockouts:
                maybe_f = next(iter(self._waiters), None)
                if maybe_f and not maybe_f.done():
                    maybe_f.set_result(None)

    async def __aexit__(self, *_dont_care: object) -> None:
        maybe_f = next(iter(self._waiters), None)
        if maybe_f and not maybe_f.done():
            maybe_f.set_result(None)
