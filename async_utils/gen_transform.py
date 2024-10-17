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
from collections.abc import AsyncGenerator, Callable, Generator
from typing import ParamSpec, TypeVar

__all__ = ["sync_to_async_gen"]

P = ParamSpec("P")
YieldType = TypeVar("YieldType")


def _consumer(
    loop: asyncio.AbstractEventLoop,
    queue: asyncio.Queue[YieldType],
    f: Callable[P, Generator[YieldType]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> None:
    for val in f(*args, **kwargs):
        loop.call_soon_threadsafe(queue.put_nowait, val)


def sync_to_async_gen(
    f: Callable[P, Generator[YieldType]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> AsyncGenerator[YieldType]:
    """async iterate over synchronous generator ran in backgroun thread.

    Generator function and it's arguments must be threadsafe.

    Generators which perform cpu intensive work while holding the GIL will
    likely not see a benefit.

    Generators which rely on two-way communication (generators as coroutines)
    are not appropriate for this function. similarly, generator return values
    are completely swallowed.

    If your generator is actually a synchronous coroutine, that's super cool,
    but rewrite is as a native coroutine or use it directly then, you don't need
    what this function does."""
    q: asyncio.Queue[YieldType] = asyncio.Queue()

    background_coro = asyncio.to_thread(_consumer, asyncio.get_running_loop(), q, f, *args, **kwargs)
    background_task = asyncio.create_task(background_coro)

    async def gen() -> AsyncGenerator[YieldType]:
        while not background_task.done():
            q_get = asyncio.ensure_future(q.get())
            done, _pending = await asyncio.wait((background_task, q_get), return_when=asyncio.FIRST_COMPLETED)
            if q_get in done:
                yield (await q_get)
        while not q.empty():
            yield q.get_nowait()
        # ensure errors in the generator propogate *after* the last values yielded
        await background_task

    return gen()
