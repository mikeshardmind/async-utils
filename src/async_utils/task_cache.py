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
import inspect
from collections.abc import Callable, Coroutine, Hashable
from functools import partial, wraps
from typing import Any

from ._paramkey import make_key
from .lru import LRU

__all__ = ("lrutaskcache", "taskcache")


# Use below doesn't accept non-task Futures, so can't accept general awaitables
type CoroFunc[**P, R] = Callable[P, Coroutine[Any, Any, R]]
type TaskFunc[**P, R] = CoroFunc[P, R] | Callable[P, asyncio.Task[R]]
type TaskCoroFunc[**P, R] = CoroFunc[P, R] | TaskFunc[P, R]

type Deco[**P, R] = Callable[[TaskCoroFunc[P, R]], TaskFunc[P, R]]

# Non-annotation assignments for transformed functions
_WRAP_ASSIGN = ("__module__", "__name__", "__qualname__", "__doc__")


def taskcache[**P, R](ttl: float | None = None) -> Deco[P, R]:
    """Cache the results of the decorated coroutine.

    Decorator to modify coroutine functions to instead act as functions
    returning cached tasks.

    For general use, this leaves the end user API largely the same,
    while leveraging tasks to allow preemptive caching.

    Note: This uses the args and kwargs of the original coroutine function as a
    cache key. This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when
    feasible in cases where this may matter.

    The ordering of args and kwargs matters.

    Parameters
    ----------
    ttl: float | None
        The time to live in seconds for cached results. Defaults to None (forever)

    Returns
    -------
    A decorator which wraps coroutine-like objects in functions that return
    preemptively cached tasks.
    """

    def wrapper(coro: TaskCoroFunc[P, R]) -> TaskFunc[P, R]:
        internal_cache: dict[Hashable, asyncio.Task[R]] = {}

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.pop, key)

        @wraps(coro, assigned=_WRAP_ASSIGN)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            key = make_key(args, kwargs)
            if (cached := internal_cache.get(key)) is not None:
                return cached

            c = coro(*args, **kwargs)
            internal_cache[key] = task = asyncio.ensure_future(c)
            cb = partial(_internal_cache_evict, key)
            task.add_done_callback(cb)
            return task

        new_sig = sig = inspect.signature(coro)
        if inspect.iscoroutinefunction(coro):
            if sig.return_annotation is not inspect.Signature.empty:
                new_ret_ann = asyncio.Task[sig.return_annotation]
            else:
                new_ret_ann = asyncio.Task

            new_sig = sig.replace(return_annotation=new_ret_ann)

        wrapped.__signature__ = new_sig  # pyright: ignore[reportAttributeAccessIssue]

        return wrapped

    return wrapper


def lrutaskcache[**P, R](ttl: float | None = None, maxsize: int = 1024) -> Deco[P, R]:
    """Cache the results of the decorated coroutine.

    Decorator to modify coroutine functions to instead act as functions
    returning cached tasks.

    For general use, this leaves the end user API largely the same,
    while leveraging tasks to allow preemptive caching.

    Note: This uses the args and kwargs of the original coroutine function as a
    cache key. This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when
    feasible in cases where this may matter.

    The ordering of args and kwargs matters.

    tasks are evicted by LRU and ttl.

    Parameters
    ----------
    ttl: float | None
        The time to live in seconds for cached results.
        Defaults to None (forever)
    maxsize: int
        The maximum number of items to retain no matter if they have reached
        expiration by ttl or not.
        Items evicted by this policy are evicted by least recent use.

    Returns
    -------
    A decorator which wraps coroutine-like objects in functions that return
    preemptively cached tasks.
    """

    def wrapper(coro: TaskCoroFunc[P, R]) -> TaskFunc[P, R]:
        internal_cache: LRU[Hashable, asyncio.Task[R]] = LRU(maxsize)

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.remove, key)

        @wraps(coro, assigned=_WRAP_ASSIGN)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            key = make_key(args, kwargs)
            if (cached := internal_cache.get(key, None)) is not None:
                return cached

            c = coro(*args, **kwargs)
            internal_cache[key] = task = asyncio.ensure_future(c)
            cb = partial(_internal_cache_evict, key)
            task.add_done_callback(cb)
            return task

        new_sig = sig = inspect.signature(coro)
        if inspect.iscoroutinefunction(coro):
            if sig.return_annotation is not inspect.Signature.empty:
                new_ret_ann = asyncio.Task[sig.return_annotation]
            else:
                new_ret_ann = asyncio.Task

            new_sig = sig.replace(return_annotation=new_ret_ann)

        wrapped.__signature__ = new_sig  # pyright: ignore[reportAttributeAccessIssue]

        return wrapped

    return wrapper
