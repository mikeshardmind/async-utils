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

"""Competing implementations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

from async_utils import _typings as t


async def merge_gens[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised, they are reraised interrupting further iteration,
    after yielding the values that are already available.
    This closes the async generators upon finishing, even if they aren't fully consumed.
    """
    cancelled: bool = False
    sentinel = object()
    futs: list[asyncio.Future[t.Any] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]

    try:
        while any(futs):
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)
            any_base_exception = False
            exceptions: list[t.Any] = []

            for f in done:
                if (not cancelled) and f.cancelled():
                    cancelled = True
                    for p in pending:
                        p.cancel()
                elif exc := f.exception():
                    if isinstance(exc, BaseException):
                        any_base_exception = True
                    exceptions.append(exc)
                else:
                    idx = futs.index(f)
                    v = f.result()
                    if v is sentinel:
                        futs[idx] = None
                    else:
                        yield v
                        futs[idx] = asyncio.ensure_future(anext(gens[idx], sentinel))

            if exceptions:
                msg = "While iterating merged async generators: "
                typ = BaseExceptionGroup if any_base_exception else ExceptionGroup
                raise typ(msg, exceptions)

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()
        # We just need to ensure these are closed for consistency in behavior
        # between error cases. Namely, avoiding non-determinism on if generators
        # are resumable based on when an error happened.
        # This also ensures that users don't need to wrap passed generators with
        # aclosing themselves.
        # AsyncGenerator.aclose being a coroutine is unfortunate,
        # but this has to be awaited to ensure the consistency of behavior.
        await asyncio.gather(*(g.aclose() for g in gens), return_exceptions=True)


async def _consumer[T](queue: asyncio.Queue[tuple[T, asyncio.Event]], gen: AsyncGenerator[T]) -> None:
    ev = asyncio.Event()
    async for value in gen:
        ev.clear()
        queue.put_nowait((value, ev))
        await ev.wait()


async def merge_gens2[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Competing implementation with the above."""

    queue: asyncio.Queue[tuple[T, asyncio.Event]] = asyncio.Queue()
    tasks = {asyncio.create_task(_consumer(queue, gen)) for gen in gens}
    any_err = asyncio.create_task(asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION))
    all_done = asyncio.create_task(asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED))

    exceptions: list[t.Any] = []
    cancelled = False

    try:
        while not all_done.done():
            q_fut = asyncio.ensure_future(queue.get())
            done, _pending = await asyncio.wait((q_fut, any_err, all_done))

            if q_fut in done:
                if q_fut.cancelled():
                    cancelled = True
                elif exc := q_fut.exception():
                    exceptions.append(exc)
                else:
                    val, ev = q_fut.result()
                    yield val
                    ev.set()
            if any_err in done:
                errdone, _ = any_err.result()
                for errtask in errdone:
                    if errtask.cancelled():
                        cancelled = True
                    elif exc := errtask.exception():
                        exceptions.append(exc)

            if exceptions:
                break

        while True:
            try:
                val, ev = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                yield val

    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

    if cancelled:
        exceptions.append(RuntimeError("Internal task cancelled unexpectedly"))
    if exceptions:
        msg = "While iterating merged async generators: "
        b = any(isinstance(e, BaseException) for e in exceptions)
        typ = BaseExceptionGroup if b else ExceptionGroup
        raise typ(msg, exceptions)
