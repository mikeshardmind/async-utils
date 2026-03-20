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
from collections.abc import AsyncGenerator


async def _consumer[T](queue: asyncio.Queue[T], gen: AsyncGenerator[T]):
    async for value in gen:
        await queue.put(value)


async def merge_gens[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:

    q: asyncio.Queue[T] = asyncio.Queue()

    gen_futs = {asyncio.ensure_future(_consumer(q, gen)) for gen in gens}

    exc_fut = asyncio.ensure_future(asyncio.wait(gen_futs, return_when=asyncio.FIRST_EXCEPTION))
    done_fut = asyncio.ensure_future(asyncio.wait(gen_futs, return_when=asyncio.ALL_COMPLETED))

    try:
        while not done_fut.done():
            q_fut = asyncio.ensure_future(q.get())

            done, _pending = await asyncio.wait((q_fut, exc_fut, done_fut), return_when=asyncio.FIRST_COMPLETED)
            if exc_fut in done:
                err, _pending = exc_fut.result()
                msg = "While iterating merged async iterators: "
                exceptions = [exc for e in err if (exc := e.exception())]
                if exceptions:
                    if len(exceptions) == 1:
                        raise exceptions[0]
                    if any(isinstance(exc, BaseException) for exc in exceptions):
                        raise BaseExceptionGroup(msg, exceptions)
                    raise ExceptionGroup(msg, exceptions)  # pyright: ignore[reportArgumentType]

            if q_fut in done:
                yield q_fut.result()

        while True:
            try:
                y = q.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                yield y
    finally:
        all_futures: set[asyncio.Task[object]] = {*gen_futs, exc_fut, done_fut}
        for fut in all_futures:
            if not fut.done():
                fut.cancel()
        await asyncio.gather(*all_futures, return_exceptions=True)
