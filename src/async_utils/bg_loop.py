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
import concurrent.futures as cf
import threading
from collections.abc import Coroutine, Generator
from contextlib import contextmanager

from . import _typings as t

type CoroReturning[R] = Coroutine[t.Any, t.Any, R]

__all__ = ("threaded_loop",)


class LoopWrapper:
    """Provides managed access to an event loop created with ``threaded_loop``.

    This is not meant to be constructed manually
    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop: asyncio.AbstractEventLoop = loop
        self._futures: set[cf.Future[t.Any]] = set()

    def schedule[T](self, coro: CoroReturning[T], /) -> cf.Future[T]:
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
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        self._futures.add(future)
        future.add_done_callback(self._futures.discard)
        return future

    async def run[T](self, coro: CoroReturning[T], /) -> T:
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
        self._futures.add(future)
        future.add_done_callback(self._futures.discard)
        return await asyncio.wrap_future(future)

    def cancel_all(self) -> None:
        """Cancel all remaining futures."""
        for future in self._futures:
            future.cancel()

    def wait_sync(self, timeout: float | None) -> bool:
        """Wait for remaining futures.

        Parameters
        ----------
        timeout: float | None
            Optionally, how long to wait for

        Returns
        -------
        bool
            True if all futures finished, otherwise False
        """
        _done, pending = cf.wait(self._futures, timeout=timeout)
        return not pending


def _run_forever(
    loop: asyncio.AbstractEventLoop,
    /,
    *,
    eager: bool = True,
) -> None:
    asyncio.set_event_loop(loop)
    if eager:
        loop.set_task_factory(asyncio.eager_task_factory)
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        tasks = {t for t in asyncio.all_tasks(loop) if not t.done()}
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
    *, use_eager_task_factory: bool = True, wait_on_exit: bool = True
) -> Generator[LoopWrapper, None, None]:
    """Create and use a managed event loop in a backround thread.

    Starts an event loop on a background thread,
    and yields an object with scheduling methods for interacting with
    the loop.

    At context manager exit, if wait_on_exit is True (default), then
    the context manager waits on the remaining futures. When it is done, or
    if that parameter is False, the loop is event loop is scheduled for shutdown
    and the thread is joined.

    Yields
    ------
    LoopWrapper
        A wrapper with methods for interacting with the background loop.
    """
    loop = asyncio.new_event_loop()
    thread = None
    wrapper = None
    try:
        args, kwargs = (loop,), {"eager": use_eager_task_factory}
        thread = threading.Thread(target=_run_forever, args=args, kwargs=kwargs)
        thread.start()
        wrapper = LoopWrapper(loop)
        yield wrapper
    finally:
        if wrapper and wait_on_exit:
            wrapper.wait_sync(None)
        loop.call_soon_threadsafe(loop.stop)
        if thread:
            thread.join()
