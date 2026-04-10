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
    cancelled: bool = False
    sentinel: t.Any = object()
    futs: list[asyncio.Task[T] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]
    exceptions: list[t.Any] = []

    try:
        while any(futs) and not cancelled:
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)

            for f in done:
                if f.cancelled():
                    if not cancelled:
                        cancelled = True
                        for p in pending:
                            p.cancel()
                elif exc := f.exception():
                    exceptions.append(exc)
                    idx = futs.index(f)
                    futs[idx] = None
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
            raise BaseExceptionGroup(msg, exceptions)

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()


async def merge_gens_suppressing_exceptions[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised internally by the generators, they are supressed.
    And all remaining generators continue being consumed.
    """
    cancelled: bool = False
    sentinel: t.Any = object()
    futs: list[asyncio.Task[T] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]

    try:
        while any(futs) and not cancelled:
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)

            for f in done:
                if f.cancelled():
                    if not cancelled:
                        cancelled = True
                        for p in pending:
                            p.cancel()
                elif f.exception():
                    idx = futs.index(f)
                    futs[idx] = None
                else:
                    idx = futs.index(f)
                    v = f.result()
                    if v is sentinel:
                        futs[idx] = None
                    else:
                        yield v
                        futs[idx] = asyncio.ensure_future(anext(gens[idx], sentinel))

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()


async def merge_gens[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[T]:
    """Creates an async generator which yields values as available from multiple.

    If any exceptions are raised, they are reraised interrupting further iteration,
    after yielding the values that are already available.
    This closes the async generators upon finishing, even if they aren't fully consumed.
    """
    cancelled: bool = False
    sentinel: t.Any = object()
    futs: list[asyncio.Task[T] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]

    try:
        while any(futs) and not cancelled:
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)
            exceptions: list[t.Any] = []

            for f in done:
                if f.cancelled():
                    if not cancelled:
                        cancelled = True
                        for p in pending:
                            p.cancel()
                elif exc := f.exception():
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
                raise BaseExceptionGroup(msg, exceptions)

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()


async def batch_merge_gens_delaying_exceptions[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[list[T]]:
    """Creates an async generator which yields batches of values as available from multiple.

    If any exceptions are raised, they are reraised
    after yielding the values consumable from the remaining generators.

    This should be used with caution, In the case of one or more infinite generators,
    an exception will not end up reraised.
    This closes the async generators upon finishing, even if they aren't fully consumed.
    """
    cancelled: bool = False
    sentinel: t.Any = object()
    futs: list[asyncio.Task[T] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]
    exceptions: list[t.Any] = []
    needs_next: list[bool] = [False for _ in gens]

    try:
        while any(futs) and not cancelled:
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)
            results: list[T] = []

            for f in done:
                if f.cancelled():
                    if not cancelled:
                        cancelled = True
                        for p in pending:
                            p.cancel()
                elif exc := f.exception():
                    exceptions.append(exc)
                    idx = futs.index(f)
                    futs[idx] = None
                else:
                    idx = futs.index(f)
                    v = f.result()
                    if v is sentinel:
                        futs[idx] = None
                    else:
                        results.append(v)
                        needs_next[idx] = True

            if results:
                yield results

            for idx, val in enumerate(needs_next):
                if val:
                    futs[idx] = asyncio.ensure_future(anext(gens[idx], sentinel))
                    needs_next[idx] = False

        if exceptions:
            msg = "While iterating merged async generators: "
            raise BaseExceptionGroup(msg, exceptions)

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()


async def batch_merge_gens_suppressing_exceptions[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[list[T]]:
    """Creates an async generator which yields batches of values as available from multiple.

    If any exceptions are raised internally by the generators, they are supressed.
    And all remaining generators continue being consumed.
    """
    cancelled: bool = False
    sentinel: t.Any = object()
    futs: list[asyncio.Task[T] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]
    needs_next: list[bool] = [False for _ in gens]

    try:
        while any(futs) and not cancelled:
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)
            results: list[T] = []

            for f in done:
                if f.cancelled():
                    if not cancelled:
                        cancelled = True
                        for p in pending:
                            p.cancel()
                elif f.exception():
                    idx = futs.index(f)
                    futs[idx] = None
                else:
                    idx = futs.index(f)
                    v = f.result()
                    if v is sentinel:
                        futs[idx] = None
                    else:
                        results.append(v)
                        needs_next[idx] = True

            if results:
                yield results

            for idx, val in enumerate(needs_next):
                if val:
                    futs[idx] = asyncio.ensure_future(anext(gens[idx], sentinel))
                    needs_next[idx] = False

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()


async def batch_merge_gens[T](*gens: AsyncGenerator[T]) -> AsyncGenerator[list[T]]:
    """Creates an async generator which yields batches of values as available from multiple.

    If any exceptions are raised, they are reraised interrupting further iteration,
    after yielding the values that are already available.
    This closes the async generators upon finishing, even if they aren't fully consumed.
    """
    cancelled: bool = False
    sentinel: t.Any = object()
    futs: list[asyncio.Task[T] | None] = [asyncio.ensure_future(anext(g, sentinel)) for g in gens]
    needs_next: list[bool] = [False for _ in gens]

    try:
        while any(futs) and not cancelled:
            done, pending = await asyncio.wait(filter(None, futs), return_when=asyncio.FIRST_COMPLETED)
            results: list[T] = []
            exceptions: list[t.Any] = []

            for f in done:
                if f.cancelled():
                    if not cancelled:
                        cancelled = True
                        for p in pending:
                            p.cancel()
                elif exc := f.exception():
                    exceptions.append(exc)
                else:
                    idx = futs.index(f)
                    v = f.result()
                    if v is sentinel:
                        futs[idx] = None
                    else:
                        results.append(v)
                        needs_next[idx] = True

            if results:
                yield results

            if exceptions:
                msg = "While iterating merged async generators: "
                raise BaseExceptionGroup(msg, exceptions)

            for idx, val in enumerate(needs_next):
                if val:
                    futs[idx] = asyncio.ensure_future(anext(gens[idx], sentinel))
                    needs_next[idx] = False

    finally:
        for f in futs:
            if f and not f.done():
                f.cancel()
