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

"""Background loop management."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Generator
from concurrent.futures import Future
from contextlib import contextmanager

type _FutureLike[T] = asyncio.Future[T] | Awaitable[T]

__all__ = ["threaded_loop"]


class LoopWrapper:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def schedule[T](self, coro: _FutureLike[T], /) -> Future[T]:
        """Schedule a coroutine to run on the wrapped event loop.

        Parameters
        ----------
        coro:
            A thread-safe coroutine-like object

        Returns
        -------
        asyncio.Future:
            A Future wrapping the result.
        """
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def run[T](self, coro: _FutureLike[T], /) -> T:
        """Schedule and await a coroutine to run on the background loop.

        Parameters
        ----------
        coro:
            A thread-safe coroutine-like object

        Returns
        -------
        The returned value of the coroutine run in the background
        """
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
        tasks: set[asyncio.Task[object]] = {
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

    Loop is scheduled for shutdown, and thread is joined at contextmanager exit

    Yields
    ------
    LoopWrapper
        A wrapper with methods for interacting with the background loop.
    """
    loop = asyncio.new_event_loop()
    thread = None
    try:
        thread = threading.Thread(
            target=run_forever,
            args=(loop,),
            kwargs={"use_eager_task_factory": use_eager_task_factory},
        )
        thread.start()
        yield LoopWrapper(loop)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        if thread:
            thread.join()
