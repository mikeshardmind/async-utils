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
import inspect  # This import is *always* used in the decorators below
from collections.abc import Callable, Coroutine, Hashable
from functools import partial, wraps
from types import MethodType

from . import _typings as t
from ._paramkey import make_key
from .lru import LRU

__all__ = ("get_stats", "lrutaskcache", "reset_stats", "taskcache")


class CacheStats:
    __slots__ = ("hits", "misses")

    def __init__(self, hits: int = 0, misses: int = 0) -> None:
        self.hits = hits
        self.misses = misses

    def __repr__(self) -> str:
        return f"CacheStats(hits={self.hits}, misses={self.misses})"


# Use below doesn't accept non-task Futures, so can't accept general awaitables
type CoroFunc[**P, R] = Callable[P, Coroutine[t.Any, t.Any, R]]
type TaskFunc[**P, R] = CoroFunc[P, R] | Callable[P, asyncio.Task[R]]
type TaskCoroFunc[**P, R] = CoroFunc[P, R] | TaskFunc[P, R]

type _CT_RET = tuple[tuple[t.Any, ...], dict[str, t.Any]]
type CacheTransformer = Callable[[tuple[t.Any, ...], dict[str, t.Any]], _CT_RET]

type Deco[**P, R] = Callable[[TaskCoroFunc[P, R]], TaskFunc[P, R]]

# Non-annotation assignments for transformed functions
_WRAP_ASSIGN = ("__module__", "__name__", "__qualname__", "__doc__")


def taskcache[**P, R](
    ttl: float | None = None,
    *,
    cache_transform: CacheTransformer | None = None,
) -> Deco[P, R]:
    """Cache the results of the decorated coroutine.

    Decorator to modify coroutine functions to instead act as functions
    returning cached tasks.

    For general use, this leaves the end user API largely the same,
    while leveraging tasks to allow preemptive caching.

    Note: This by default uses the args and kwargs of the original coroutine
    function as a cache key. This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when
    feasible in cases where this may matter, or using a cache transform.

    The ordering of args and kwargs matters.

    Parameters
    ----------
    ttl: float | None
        The time to live in seconds for cached results. Defaults to None (forever)
    cache_transform: CacheTransformer | None
        An optional callable that transforms args and kwargs used
        as a cache key.

    Returns
    -------
    A decorator which wraps coroutine-like objects in functions that return
    preemptively cached tasks.
    """
    if cache_transform is None:
        key_func = make_key
    else:

        def key_func(args: tuple[t.Any, ...], kwds: dict[t.Any, t.Any]) -> Hashable:
            return make_key(*cache_transform(args, kwds))

    stats = CacheStats()

    def wrapper(coro: TaskCoroFunc[P, R]) -> TaskFunc[P, R]:
        internal_cache: dict[Hashable, asyncio.Task[R]] = {}

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.pop, key)

        @wraps(coro, assigned=_WRAP_ASSIGN)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            key = key_func(args, kwargs)
            if (cached := internal_cache.get(key)) is not None:
                stats.hits += 1
                return cached

            stats.misses += 1

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

        def hits(_self: object) -> int:
            return stats.hits

        def misses(_self: object) -> int:
            return stats.misses

        def reset_stats(_self: object) -> None:
            stats.hits = stats.misses = 0

        wrapped.hits = MethodType(hits, wrapped)  # pyright: ignore[reportAttributeAccessIssue]
        wrapped.misses = MethodType(misses, wrapped)  # pyright: ignore[reportAttributeAccessIssue]
        wrapped.reset_stats = MethodType(reset_stats, wrapped)  # pyright: ignore[reportAttributeAccessIssue]

        return wrapped

    return wrapper


def lrutaskcache[**P, R](
    ttl: float | None = None,
    maxsize: int = 1024,
    *,
    cache_transform: CacheTransformer | None = None,
) -> Deco[P, R]:
    """Cache the results of the decorated coroutine.

    Decorator to modify coroutine functions to instead act as functions
    returning cached tasks.

    For general use, this leaves the end user API largely the same,
    while leveraging tasks to allow preemptive caching.

    Note: This by default uses the args and kwargs of the original coroutine
    function as a cache key. This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when
    feasible in cases where this may matter, or using a cache transform.

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
    cache_transform: CacheTransformer | None
        An optional callable that transforms args and kwargs used
        as a cache key.

    Returns
    -------
    A decorator which wraps coroutine-like objects in functions that return
    preemptively cached tasks.
    """
    if cache_transform is None:
        key_func = make_key
    else:

        def key_func(args: tuple[t.Any, ...], kwds: dict[t.Any, t.Any]) -> Hashable:
            return make_key(*cache_transform(args, kwds))

    stats = CacheStats()

    def wrapper(coro: TaskCoroFunc[P, R]) -> TaskFunc[P, R]:
        internal_cache: LRU[Hashable, asyncio.Task[R]] = LRU(maxsize)

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.remove, key)

        @wraps(coro, assigned=_WRAP_ASSIGN)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            key = key_func(args, kwargs)
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

        def hits(_self: object) -> int:
            return stats.hits

        def misses(_self: object) -> int:
            return stats.misses

        def reset_stats(_self: object) -> None:
            stats.hits = stats.misses = 0

        wrapped.hits = MethodType(hits, wrapped)  # pyright: ignore[reportAttributeAccessIssue]
        wrapped.misses = MethodType(misses, wrapped)  # pyright: ignore[reportAttributeAccessIssue]
        wrapped.reset_stats = MethodType(reset_stats, wrapped)  # pyright: ignore[reportAttributeAccessIssue]

        return wrapped

    return wrapper


def get_stats(f: Deco[..., t.Any]) -> CacheStats:
    """Get cache stats from a decorated function.

    Raises
    ------
    LookupError

    Returns
    -------
    CacheStats
    """
    try:
        return CacheStats(f.hits(), f.misses())  # pyright: ignore[reportFunctionMemberAccess]
    except AttributeError:
        raise LookupError from None


def reset_stats(f: Deco[..., t.Any]) -> None:
    """Reset cache stats from a decorated function.

    Raises
    ------
    LookupError
    """
    try:
        f.reset_stats()  # pyright: ignore[reportFunctionMemberAccess]
    except AttributeError:
        raise LookupError from None
