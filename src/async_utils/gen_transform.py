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
import concurrent.futures as cf  #: PYUPDATE: py3.14, check cf.Future use
from asyncio import FIRST_COMPLETED as FC
from collections.abc import AsyncGenerator, Callable, Generator
from threading import Event

from . import _typings as t
from ._qs import Queue

__all__ = ("ACTX", "sync_to_async_gen", "sync_to_async_gen_noctx")


def _consumer[**P, Y](
    laziness_ev: Event,
    queue: Queue[Y],
    cancel_future: cf.Future[None],
    f: Callable[P, Generator[Y]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> None:
    try:
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
    except StopIteration:
        pass


type _ConGen[**P, Y] = Callable[P, Generator[Y]]
type ConsumerType[**P, Y] = Callable[
    t.Concatenate[Event, Queue[Y], cf.Future[None], _ConGen[P, Y], P], None
]


class ACTX[Y]:
    """Context manager to forward exception context to generator in thread.

    Not intended for public construction.
    """

    __final__ = True

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this."
        raise RuntimeError(msg)

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
    ) -> None:
        if exc_value is not None:
            self.f.set_exception(exc_value)

        await self.g.aclose()


def _sync_to_async_gen[**P, Y](
    f: Callable[P, Generator[Y]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> tuple[AsyncGenerator[Y], cf.Future[None]]:
    # TODO: consider shutdownable queue rather than the double event use
    # needs to be a seperate queue if so, shutdown requires explicit sync
    q: Queue[Y] = Queue(maxsize=1)
    lazy_ev = Event()  # used to preserve generator laziness
    lazy_ev.set()
    cancel_fut: cf.Future[None] = cf.Future()
    c: ConsumerType[P, Y] = _consumer

    bg_coro = asyncio.to_thread(c, lazy_ev, q, cancel_fut, f, *args, **kwargs)
    bg_task = asyncio.create_task(bg_coro)

    async def gen() -> AsyncGenerator[Y]:
        q_get = None
        try:
            while not bg_task.done():
                try:
                    q_get = asyncio.ensure_future(q.async_get())
                    done, _ = await asyncio.wait((bg_task, q_get), return_when=FC)
                    if q_get in done:
                        lazy_ev.clear()
                        yield (await q_get)
                        lazy_ev.set()
                finally:
                    if q_get is not None:
                        q_get.cancel()

        finally:
            try:
                cancel_fut.set_result(None)
            except cf.InvalidStateError:
                pass
            lazy_ev.set()
            while q:
                yield (await q.async_get())
            # ensure errors in the generator propogate *after* the last values yielded
            await bg_task

    return gen(), cancel_fut


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
    return ACTX(*_sync_to_async_gen(f, *args, **kwargs))


def sync_to_async_gen_noctx[**P, Y](
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

    This version does not forward exception context and is not a context manager.

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
    AsyncGenerator[Y]
    """
    gen, _fut = _sync_to_async_gen(f, *args, **kwargs)
    return gen
