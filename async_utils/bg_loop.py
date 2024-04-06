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
from typing import Any, TypeAlias, TypeVar

_T = TypeVar("_T")

_FutureLike: TypeAlias = asyncio.Future[_T] | Generator[Any, None, _T] | Awaitable[_T]

__all__ = ["threaded_loop"]


class LoopWrapper:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def schedule(self, coro: _FutureLike[_T]) -> Future[_T]:
        """Schedule a coroutine to run on the wrapped event loop"""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def run(self, coro: _FutureLike[_T]) -> _T:
        """Schedule a coroutine to run on the background loop,
        awaiting it finishing."""

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        finished = threading.Event()

        def future_done_callback(_f: Future[Any]) -> object:
            finished.set()

        future.add_done_callback(future_done_callback)

        await asyncio.get_running_loop().run_in_executor(None, finished.wait)
        return future.result()


def run_forever(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(asyncio.sleep(0.05))
        tasks: set[asyncio.Task[Any]] = {t for t in asyncio.all_tasks(loop) if not t.done()}
        for t in tasks:
            t.cancel()
        loop.run_until_complete(asyncio.sleep(0))
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.run_until_complete(loop.shutdown_default_executor())

        for task in tasks:
            try:
                if (exc := task.exception()) is not None:
                    loop.call_exception_handler(
                        {
                            "message": "Unhandled exception in task during shutdown.",
                            "exception": task.exception(),
                            "task": exc,
                        }
                    )
            except (asyncio.InvalidStateError, asyncio.CancelledError):
                pass

        asyncio.set_event_loop(None)
        loop.close()


@contextmanager
def threaded_loop():
    loop = asyncio.new_event_loop()
    thread = None
    try:
        thread = threading.Thread(target=run_forever, args=(loop,))
        thread.start()
        yield LoopWrapper(loop)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        if thread:
            thread.join()
