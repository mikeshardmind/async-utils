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
import threading
from collections.abc import Awaitable, Generator
from concurrent.futures import Future
from contextlib import contextmanager
from typing import Any, TypeVar

_T = TypeVar("_T")

type _FutureLike[_T] = asyncio.Future[_T] | Awaitable[_T]

__all__ = ["threaded_loop"]


class LoopWrapper:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)

    def schedule(self, coro: _FutureLike[_T]) -> Future[_T]:
        """Schedule a coroutine to run on the wrapped event loop."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def run(self, coro: _FutureLike[_T]) -> _T:
        """Schedule and await a coroutine to run on the background loop."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(future)


def run_forever(
    loop: asyncio.AbstractEventLoop,
    /,
    *,
    use_eager_task_factory: bool = True,
) -> None:
    asyncio.set_event_loop(loop)
    if use_eager_task_factory:
        loop.set_task_factory(asyncio.eager_task_factory)
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        tasks: set[asyncio.Task[Any]] = {
            t for t in asyncio.all_tasks(loop) if not t.done()
        }
        for t in tasks:
            t.cancel()
        loop.run_until_complete(asyncio.sleep(0))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())

        for task in tasks:
            try:
                if (exc := task.exception()) is not None:
                    loop.call_exception_handler({
                        "message": "Unhandled exception in task during shutdown.",
                        "exception": exc,
                        "task": task,
                    })
            except (asyncio.InvalidStateError, asyncio.CancelledError):
                pass

        asyncio.set_event_loop(None)
        loop.close()


@contextmanager
def threaded_loop(
    *, use_eager_task_factory: bool = True
) -> Generator[LoopWrapper, None, None]:
    """Create and use a managed event loop in a backround thread.

    Starts an event loop on a background thread,
    and yields an object with scheduling methods for interacting with
    the loop.

    loop is scheduled for shutdown, and thread is joined at contextmanager exit
    """
    loop = asyncio.new_event_loop()
    thread = None
    try:
        thread = threading.Thread(
            target=run_forever, args=(loop, use_eager_task_factory)
        )
        thread.start()
        yield LoopWrapper(loop)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        if thread:
            thread.join()
