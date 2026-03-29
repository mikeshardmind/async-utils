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

from . import _typings as t

# The implementations here are extremely similar. If changing one for any reason,
# make sure the others don't need changes.
# This is preferred over a kwarg dictating branching behavior internally.


async def merge_gens_delaying_exceptions[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised, they are reraised
    after yielding the values consumable from the remaining generators.

    This should be used with caution, In the case of one or more infinite generators,
    an exception will not end up reraised.
    This closes the async generators upon finishing, even if they aren't fully consumed.
    """
    all_done: set[AsyncGenerator[T]] = set()
    cancelled: bool = False
    sentinel = object()
    futs: dict[asyncio.Future[t.Any], AsyncGenerator[T]] = {asyncio.ensure_future(anext(g, sentinel)): g for g in gens}
    any_base_exception = False
    exceptions: list[t.Any] = []

    try:
        while futs:
            done, pending = await asyncio.wait(futs, return_when=asyncio.FIRST_COMPLETED)

            done_gens: set[AsyncGenerator[T]] = set()

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
                    v = f.result()
                    if v is sentinel:
                        all_done.add(futs[f])
                    else:
                        yield v
                        done_gens.add(futs[f])

            pending_map = {p: futs[p] for p in pending}
            futs = {asyncio.ensure_future(anext(g, sentinel)): g for g in done_gens if g not in all_done}
            futs.update(pending_map)

        if exceptions:
            msg = "While iterating merged async generators: "
            typ = BaseExceptionGroup if any_base_exception else ExceptionGroup
            raise typ(msg, exceptions)

    finally:
        for f in futs:
            if not f.done():
                f.cancel()
        # We just need to ensure these are closed for consistency in behavior
        # between error cases. Namely, avoiding non-determinism on if generators
        # are resumable based on when an error happened.
        # This also ensures that users don't need to wrap passed generators with
        # aclosing themselves.
        # AsyncGenerator.aclose being a coroutine is unfortunate,
        # but this has to be awaited to ensure the consistency of behavior.
        await asyncio.gather(*(g.aclose() for g in gens), return_exceptions=True)


async def merge_gens_suppressing_exceptions[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised internally by the generators, they are supressed.
    And all remaining generators continue being consumed.
    """
    all_done: set[AsyncGenerator[T]] = set()
    cancelled: bool = False
    sentinel = object()
    futs: dict[asyncio.Future[t.Any], AsyncGenerator[T]] = {asyncio.ensure_future(anext(g, sentinel)): g for g in gens}

    try:
        while futs:
            done, pending = await asyncio.wait(futs, return_when=asyncio.FIRST_COMPLETED)
            done_gens: set[AsyncGenerator[T]] = set()

            for f in done:
                if (not cancelled) and f.cancelled():
                    cancelled = True
                elif f.exception():
                    all_done.add(futs[f])
                else:
                    v = f.result()
                    if v is sentinel:
                        all_done.add(futs[f])
                    else:
                        yield v
                        done_gens.add(futs[f])

            pending_map = {p: futs[p] for p in pending}
            futs = {asyncio.ensure_future(anext(g, sentinel)): g for g in done_gens if g not in all_done}
            futs.update(pending_map)
    finally:
        for f in futs:
            if not f.done():
                f.cancel()
        # We just need to ensure these are closed for consistency in behavior
        # between error cases. Namely, avoiding non-determinism on if generators
        # are resumable based on when an error happened.
        # This also ensures that users don't need to wrap passed generators with
        # aclosing themselves.
        # AsyncGenerator.aclose being a coroutine is unfortunate,
        # but this has to be awaited to ensure the consistency of behavior.
        await asyncio.gather(*(g.aclose() for g in gens), return_exceptions=True)


async def merge_gens[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised, they are reraised interrupting further iteration,
    after yielding the values that are already available.
    This closes the async generators upon finishing, even if they aren't fully consumed.
    """
    all_done: set[AsyncGenerator[T]] = set()
    cancelled: bool = False
    sentinel = object()
    futs: dict[asyncio.Future[t.Any], AsyncGenerator[T]] = {asyncio.ensure_future(anext(g, sentinel)): g for g in gens}

    try:
        while futs:
            done, pending = await asyncio.wait(futs, return_when=asyncio.FIRST_COMPLETED)
            any_base_exception = False
            exceptions: list[t.Any] = []
            done_gens: set[AsyncGenerator[T]] = set()

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
                    v = f.result()
                    if v is sentinel:
                        all_done.add(futs[f])
                    else:
                        yield v
                        done_gens.add(futs[f])

            if exceptions:
                msg = "While iterating merged async generators: "
                typ = BaseExceptionGroup if any_base_exception else ExceptionGroup
                raise typ(msg, exceptions)

            pending_map = {p: futs[p] for p in pending}
            futs = {asyncio.ensure_future(anext(g, sentinel)): g for g in done_gens if g not in all_done}
            futs.update(pending_map)
    finally:
        for f in futs:
            if not f.done():
                f.cancel()
        # We just need to ensure these are closed for consistency in behavior
        # between error cases. Namely, avoiding non-determinism on if generators
        # are resumable based on when an error happened.
        # This also ensures that users don't need to wrap passed generators with
        # aclosing themselves.
        # AsyncGenerator.aclose being a coroutine is unfortunate,
        # but this has to be awaited to ensure the consistency of behavior.
        await asyncio.gather(*(g.aclose() for g in gens), return_exceptions=True)
