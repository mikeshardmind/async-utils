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
from functools import total_ordering
from time import time

from . import _typings as t

__all__ = ("CancellationToken", "Scheduler")

MISSING: t.Any = object()


class CancellationToken:
    """An object to use for cancelation of a task.

    Not meant for public construction.
    """

    __slots__ = ()


@total_ordering
class _Task[T]:
    __slots__ = ("cancel_token", "canceled", "payload", "timestamp")

    def __init__(self, timestamp: float, payload: T, /) -> None:
        self.timestamp: float = timestamp
        self.payload: T = payload
        self.canceled: bool = False
        self.cancel_token: CancellationToken = CancellationToken()

    def __lt__(self, other: _Task[T]) -> bool:
        return (self.timestamp, id(self)) < (other.timestamp, id(self))


class Scheduler[T]:
    """A scheduler.

    The scheduler is implemented as an async context manager that it an
    async iterator.

    Payloads can be scheduled to the context manager, and will be yielded
    by the iterator when the time for them has come.

    Parameters
    ----------
    granularity: float
        The number of seconds to compare schedule events at.
        If this is set lower than the precision of time.monotonic
        on the host system, this is effectively the same as setting
        it to time.monotonic's precision.
    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    __tasks: dict[CancellationToken, _Task[T]]
    __tqueue: asyncio.PriorityQueue[_Task[T]]
    __closed: bool
    __l: asyncio.Lock
    __granularity: float

    __slots__ = ("__closed", "__granularity", "__l", "__tasks", "__tqueue")

    def __init__(self, granularity: float, /) -> None:
        self.__granularity = granularity
        self.__closed = MISSING
        self.__tasks = MISSING
        self.__tqueue = MISSING
        self.__l = MISSING

    async def __aenter__(self) -> t.Self:
        self.__closed = False
        asyncio.get_running_loop()

        # lock is only needeed on modifying or removing tasks
        # insertion is not guarded and only racy in the order of emitted events
        # when inserting a task that is scheduled in the past
        # or within 1 full iteration of pending tasks on the event loop
        # (generally, ms range (subsecond), depending on application)
        self.__l = asyncio.Lock()
        self.__tasks = {}
        self.__tqueue = asyncio.PriorityQueue()

        return self

    async def __aexit__(self, *_dont_care: object) -> None:
        self.__closed = True

    def __aiter__(self) -> t.Self:
        return self

    async def __anext__(self) -> T:
        while await asyncio.sleep(self.__granularity, True):
            if self.__closed:
                raise StopAsyncIteration

            t = await self.__tqueue.get()
            try:
                if t.canceled:
                    continue
                now = time()
                delta = t.timestamp - now
                if delta < self.__granularity:
                    async with self.__l:
                        self.__tasks.pop(t.cancel_token, None)
                        return t.payload
                else:
                    await self.__tqueue.put(t)
            finally:
                self.__tqueue.task_done()
        raise StopAsyncIteration

    async def create_task(self, timestamp: float, payload: T, /) -> CancellationToken:
        """Create a task.

        Parameters
        ----------
        timestamp: float
            The utc timestamp for when a payload should be emitted.
        payload:
            The payload to emit

        Returns
        -------
        CancellationToken:
            An opaque object that can be used to cancel a task.
            You should not rely on details of this class's type.
        """
        t = _Task(timestamp, payload)
        self.__tasks[t.cancel_token] = t
        await self.__tqueue.put(t)
        return t.cancel_token

    async def cancel_task(self, cancel_token: CancellationToken, /) -> None:
        """Cancel a task.

        Canceling an already canceled task is not an error

        Parameters
        ----------
        cancel_token: CancellationToken
            The object which the scheduler gave you upon scheduling the task.
        """
        async with self.__l:
            try:
                task = self.__tasks[cancel_token]
                task.canceled = True
            except KeyError:
                pass

    def close(self) -> None:
        """Close the scheduler without waiting."""
        self.__closed = True

    async def join(self) -> None:
        """Wait for the scheduler's internal queue to be empty."""
        await self.__tqueue.join()
