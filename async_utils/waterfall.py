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
import time
from collections.abc import Callable, Coroutine, Sequence
from typing import Any, Generic, Literal, TypeVar, overload

T = TypeVar("T")

__all__ = ("Waterfall",)


class Waterfall(Generic[T]):
    """Class for batch event scheduling based on recurring intervals,
    with a quanity threshold which overrides the interval.

    Initial intended was batching of simple db writes with an
    acceptable tolerance for lost writes,
    though short of an application crash, this is designed
    to allow graceful shutdown to flush pending actions."""

    def __init__(
        self,
        max_wait: float,
        max_quantity: int,
        async_callback: Callable[[Sequence[T]], Coroutine[Any, Any, Any]],
        *,
        max_wait_finalize: int = 3,
    ):
        asyncio.get_running_loop()
        self.queue: asyncio.Queue[T] = asyncio.Queue()
        self.max_wait: float = max_wait
        self.max_wait_finalize: int = max_wait_finalize
        self.max_quantity: int = max_quantity
        self.callback: Callable[[Sequence[T]], Coroutine[Any, Any, Any]] = async_callback
        self.task: asyncio.Task[None] | None = None
        self._alive: bool = False

    def start(self):
        if self.task is not None:
            msg = "Already Running"
            raise RuntimeError(msg)

        self._alive = True
        self.task = asyncio.create_task(self._loop())

    @overload
    def stop(self, wait: Literal[True]) -> Coroutine[Any, Any, None]:
        pass

    @overload
    def stop(self, wait: Literal[False]) -> None:
        pass

    @overload
    def stop(self, wait: bool = False) -> Coroutine[Any, Any, None] | None:
        pass

    def stop(self, wait: bool = False) -> Coroutine[Any, Any, None] | None:
        self._alive = False
        return self.queue.join() if wait else None

    def put(self, item: T):
        if not self._alive:
            msg = "Can't put something in a non-running Waterfall."
            raise RuntimeError(msg)
        self.queue.put_nowait(item)

    async def _loop(self) -> None:
        try:
            _tasks: set[asyncio.Task[Any]] = set()
            while self._alive:
                queue_items: Sequence[T] = []
                iter_start = time.monotonic()

                while (this_max_wait := (time.monotonic() - iter_start)) < self.max_wait:
                    try:
                        n = await asyncio.wait_for(self.queue.get(), this_max_wait)
                    except TimeoutError:
                        continue
                    else:
                        queue_items.append(n)
                    if len(queue_items) >= self.max_quantity:
                        break

                    if not queue_items:
                        continue

                num_items = len(queue_items)

                t = asyncio.create_task(self.callback(queue_items))
                _tasks.add(t)
                t.add_done_callback(_tasks.remove)

                for _ in range(num_items):
                    self.queue.task_done()

        finally:
            f = asyncio.create_task(self._finalize(), name="waterfall.finalizer")
            await asyncio.wait_for(f, timeout=self.max_wait_finalize)

    async def _finalize(self) -> None:
        # WARNING: Do not allow an async context switch before the gather below

        self._alive = False
        remaining_items: Sequence[T] = []

        while not self.queue.empty():
            try:
                ev = self.queue.get_nowait()
            except asyncio.QueueEmpty:
                # we should never hit this, asyncio queues know their size reliably when used appropriately.
                break

            remaining_items.append(ev)

        if not remaining_items:
            return

        num_remaining = len(remaining_items)

        pending_futures: list[asyncio.Task[Any]] = []

        for chunk in (remaining_items[p : p + self.max_quantity] for p in range(0, num_remaining, self.max_quantity)):
            fut = asyncio.create_task(self.callback(chunk))
            pending_futures.append(fut)

        gathered = asyncio.gather(*pending_futures)

        try:
            await asyncio.wait_for(gathered, timeout=self.max_wait_finalize)
        except TimeoutError:
            for task in pending_futures:
                task.cancel()

        for _ in range(num_remaining):
            self.queue.task_done()
