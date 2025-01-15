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
from threading import Event

from ._qs import Queue

__all__ = ["sync_to_async_gen"]


def _consumer[**P, Y](
    laziness_ev: Event,
    queue: Queue[Y],
    cancel_event: Event,
    f: Callable[P, Generator[Y]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> None:
    for val in f(*args, **kwargs):
        if cancel_event.is_set():
            break
        laziness_ev.wait()
        if cancel_event.is_set():
            break
        queue.sync_put(val)
        laziness_ev.clear()
        if cancel_event.is_set():
            break


def sync_to_async_gen[**P, Y](
    f: Callable[P, Generator[Y]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> AsyncGenerator[Y]:
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

    This function is susceptible to leaving the background generator permanently
    suspended if you do not close the async generator. This isn't typically
    an issue if your application does not have pathological cancellation,
    however if you don't don't control cancellation and don't want to explain,
    to users that their cancellation semantics are unsound in python this
    function in particular should be wrapped with contextlib.aclosing.

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
    # TODO: consider shutdownable queue rather than the double event use
    # needs to be a seperate queue if so
    q: Queue[Y] = Queue(maxsize=1)
    laziness_ev = Event()  # used to preserve generator laziness
    laziness_ev.set()
    cancel_ev = Event()

    background_coro = asyncio.to_thread(
        _consumer, laziness_ev, q, cancel_ev, f, *args, **kwargs
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
                        yield (await q_get)
                        laziness_ev.set()
                finally:
                    if q_get is not None:
                        q_get.cancel()
            laziness_ev.clear()
            while q:
                yield (await q.async_get())
            # ensure errors in the generator propogate *after* the last values yielded
            await background_task
        finally:
            cancel_ev.set()
            laziness_ev.set()

    return gen()
