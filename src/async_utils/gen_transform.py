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
import concurrent.futures as cf
from collections.abc import AsyncGenerator, Callable, Generator
from threading import Event

from ._qs import Queue

__all__ = ["sync_to_async_gen"]


def _consumer[**P, Y](
    laziness_ev: Event,
    queue: Queue[Y],
    cancel_future: cf.Future[None],
    f: Callable[P, Generator[Y]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> None:
    gen = f(*args, **kwargs)

    for val in gen:
        laziness_ev.wait()
        queue.sync_put(val)
        laziness_ev.clear()

        if cancel_future.cancelled():
            gen.throw(cf.CancelledError)

        if cancel_future.done():
            if exc := cancel_future.exception():
                gen.throw(type(exc), exc)
            else:
                gen.throw(cf.CancelledError)


class ACTX[Y]:
    def __init__(self, g: AsyncGenerator[Y], f: cf.Future[None]) -> None:
        self.g = g
        self.f = f

    async def __aenter__(self) -> AsyncGenerator[Y]:
        return self.g

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> bool:
        if exc_value is not None:
            self.f.set_exception(exc_value)

        await self.g.aclose()
        return False


def sync_to_async_gen[**P, Y](
    f: Callable[P, Generator[Y]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> ACTX[Y]:
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

    .. note::

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
    ACTX
        This is an async context manager,
        that when entered, returns an async iterable.
    """
    # TODO: consider shutdownable queue rather than the double event use
    # needs to be a seperate queue if so
    q: Queue[Y] = Queue(maxsize=1)
    laziness_ev = Event()  # used to preserve generator laziness
    laziness_ev.set()
    cancel_future: cf.Future[None] = cf.Future()

    background_coro = asyncio.to_thread(
        _consumer, laziness_ev, q, cancel_future, f, *args, **kwargs
    )
    background_task = asyncio.create_task(background_coro)

    async def gen() -> AsyncGenerator[Y]:
        q_get = None
        try:
            while not background_task.done():
                try:
                    q_get = asyncio.ensure_future(q.async_get())
                    done, _pending = await asyncio.wait(
                        (background_task, q_get),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if q_get in done:
                        laziness_ev.clear()
                        yield (await q_get)
                        laziness_ev.set()
                finally:
                    if q_get is not None:
                        q_get.cancel()

        finally:
            try:
                cancel_future.set_result(None)
            except cf.InvalidStateError:
                pass
            laziness_ev.set()
            while q:
                yield (await q.async_get())
            # ensure errors in the generator propogate *after* the last values yielded
            await background_task

    return ACTX(gen(), cancel_future)
