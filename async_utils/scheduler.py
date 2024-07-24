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
from types import TracebackType
from typing import Any, Generic, TypeVar

__all__ = ("Scheduler",)

MISSING: Any = object()
T = TypeVar("T")


class CancelationToken:
    __slots__ = ()


@total_ordering
class _Task(Generic[T]):
    __slots__ = ("timestamp", "payload", "canceled", "cancel_token")

    def __init__(self, timestamp: float, payload: T, /):
        self.timestamp: float = timestamp
        self.payload: T = payload
        self.canceled: bool = False
        self.cancel_token: CancelationToken = CancelationToken()

    def __lt__(self, other: _Task[T]):
        return (self.timestamp, id(self)) < (other.timestamp, id(self))


class Scheduler(Generic[T]):
    __tasks: dict[CancelationToken, _Task[T]]
    __tqueue: asyncio.PriorityQueue[_Task[T]]
    __closed: bool
    __l: asyncio.Lock
    __granularity: float

    __slots__ = ("__tasks", "__tqueue", "__closed", "__l", "__granularity")

    def __init__(self, granularity: float, /):
        self.__granularity = granularity
        self.__closed = MISSING
        self.__tasks = MISSING
        self.__tqueue = MISSING
        self.__l = MISSING

    async def __aenter__(self):
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

    async def __aexit__(self, exc_type: type[Exception], exc: Exception, tb: TracebackType):
        self.__closed = True

    def __aiter__(self):
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

    async def create_task(self, timestamp: float, payload: T, /) -> CancelationToken:
        t = _Task(timestamp, payload)
        self.__tasks[t.cancel_token] = t
        await self.__tqueue.put(t)
        return t.cancel_token

    async def cancel_task(self, cancel_token: CancelationToken, /) -> bool:
        """Returns if the task with that uuid was cancelled. Cancelling an already cancelled task is allowed."""
        async with self.__l:
            try:
                task = self.__tasks[cancel_token]
                task.canceled = True
            except KeyError:
                pass
            else:
                return True
        return False

    def close(self):
        """Closes the scheduler without waiting"""
        self.__closed = True

    async def join(self):
        """Waits for the scheduler's internal queue to be empty"""
        await self.__tqueue.join()
