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
from collections import deque
from collections.abc import AsyncGenerator, Callable, Generator
from typing import ParamSpec, TypeVar

__all__ = ["sync_to_async_gen"]

P = ParamSpec("P")
YieldType = TypeVar("YieldType")


class _PeekableQueue[T](asyncio.Queue[T]):
    # This is for internal use only, tested on both 3.12 and 3.13
    # This will be tested for 3.14 prior to 3.14's release.

    _get_loop: Callable[[], asyncio.AbstractEventLoop]  # pyright: ignore[reportUninitializedInstanceVariable]
    _getters: deque[asyncio.Future[None]]  # pyright: ignore[reportUninitializedInstanceVariable]
    _wakeup_next: Callable[[deque[asyncio.Future[None]]], None]  # pyright: ignore[reportUninitializedInstanceVariable]
    _queue: deque[T]  # pyright: ignore[reportUninitializedInstanceVariable]

    async def peek(self) -> T:
        while self.empty():
            getter = self._get_loop().create_future()
            self._getters.append(getter)  # type:
            try:
                await getter
            except:
                getter.cancel()
                try:
                    self._getters.remove(getter)
                except ValueError:
                    pass
                if not self.empty() and not getter.cancelled():
                    self._wakeup_next(self._getters)
                raise
        return self._queue[0]


def _consumer(
    loop: asyncio.AbstractEventLoop,
    queue: _PeekableQueue[YieldType],
    f: Callable[P, Generator[YieldType]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> None:
    for val in f(*args, **kwargs):
        # This ensures a strict ordering on other event loops
        # uvloop in particular caused this to be needed
        h = asyncio.run_coroutine_threadsafe(queue.put(val), loop)
        h.result()


def sync_to_async_gen(
    f: Callable[P, Generator[YieldType]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> AsyncGenerator[YieldType]:
    """Asynchronously iterate over a synchronous generator.

    The generator function and it's arguments must be threadsafe and will be
    iterated lazily. Generators which perform cpu intensive work while holding
    the GIL will likely not see a benefit.

    Generators which rely on two-way communication (generators as coroutines)
    are not appropriate for this function. similarly, generator return values
    are completely swallowed.

    If your generator is actually a synchronous coroutine, that's super cool,
    but rewrite is as a native coroutine or use it directly then, you don't need
    what this function does.

    Parameters
    ----------
    f:
        The synchronous generator function to wrap.
    *args:
        The positional args to pass to the generator construction.
    **kwargs:
        The keyword arguments to pass to the generator construction.

    Returns
    -------
    An asynchronous iterator which yields the results of the wrapped generator.
    """
    # Provides backpressure, ensuring the underlying sync generator in a thread
    # is lazy If the user doesn't want laziness, then using this method makes
    # little sense, they could trivially exhaust the generator in a thread with
    # asyncio.to_thread(lambda g: list(g()), g) to then use the values
    q: _PeekableQueue[YieldType] = _PeekableQueue(maxsize=1)

    background_coro = asyncio.to_thread(
        _consumer, asyncio.get_running_loop(), q, f, *args, **kwargs
    )
    background_task = asyncio.create_task(background_coro)

    async def gen() -> AsyncGenerator[YieldType]:
        while not background_task.done():
            q_peek = asyncio.ensure_future(q.peek())
            done, _pending = await asyncio.wait(
                (background_task, q_peek), return_when=asyncio.FIRST_COMPLETED
            )
            if q_peek in done:
                yield (await q_peek)
                q.get_nowait()
        while not q.empty():
            yield q.get_nowait()
        # ensure errors in the generator propogate *after* the last values yielded
        await background_task

    return gen()
