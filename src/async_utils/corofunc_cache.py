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
from collections.abc import Awaitable, Callable, Coroutine, Hashable
from functools import partial, wraps

from . import _typings as t
from ._paramkey import make_key
from .lru import LRU

__all__ = ("corocache", "lrucorocache")


type CoroFunc[**P, R] = Callable[P, Coroutine[t.Any, t.Any, R]]
type CoroLike[**P, R] = Callable[P, Awaitable[R]]

type _CT_RET = tuple[tuple[t.Any, ...], dict[str, t.Any]]

#: Note CacheTransformers recieve a tuple (args) and dict(kwargs)
#: rather than a ParamSpec of the decorated function.
#: Warning: Mutating the dict will impact callsite, return a new dict instead!
type CacheTransformer = Callable[[tuple[t.Any, ...], dict[str, t.Any]], _CT_RET]

type Deco[**P, R] = Callable[[CoroLike[P, R]], CoroFunc[P, R]]


def corocache[**P, R](
    ttl: float | None = None,
    *,
    cache_transform: CacheTransformer | None = None,
) -> Deco[P, R]:
    """Cache the results of the decorated coroutine.

    This is less powerful than the version in task_cache.py but may work better
    for some cases where typing of libraries this interacts with is too
    restrictive.

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
    A decorator which wraps coroutine-like functions with preemptive caching.
    """
    if cache_transform is None:
        key_func = make_key
    else:

        def key_func(args: tuple[t.Any, ...], kwds: dict[t.Any, t.Any]) -> Hashable:
            return make_key(*cache_transform(args, kwds))

    def wrapper(coro: CoroLike[P, R]) -> CoroFunc[P, R]:
        internal_cache: dict[Hashable, asyncio.Future[R]] = {}

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.pop, key)

        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            key = key_func(args, kwargs)
            if (cached := internal_cache.get(key)) is not None:
                return await cached

            c = coro(*args, **kwargs)
            internal_cache[key] = fut = asyncio.ensure_future(c)
            cb = partial(_internal_cache_evict, key)
            fut.add_done_callback(cb)
            return await fut

        return wrapped

    return wrapper


def lrucorocache[**P, R](
    ttl: float | None = None,
    maxsize: int = 1024,
    *,
    cache_transform: CacheTransformer | None = None,
) -> Deco[P, R]:
    """Cache the results of the decorated coroutine.

    This is less powerful than the version in task_cache.py but may work better
    for some cases where typing of libraries this interacts with is too
    restrictive.

    Note: This by default uses the args and kwargs of the original coroutine
    function as a cache key. This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when
    feasible in cases where this may matter, or using a cache transform.

    The ordering of args and kwargs matters.

    Cached results are evicted by LRU and ttl.

    Parameters
    ----------
    ttl: float | None
        The time to live in seconds for cached results. Defaults to None (forever)
    maxsize: int
        The maximum number of items to retain no matter if they have reached
        expiration by ttl or not.
        Items evicted by this policy are evicted by least recent use.
    cache_transform: CacheTransformer | None
        An optional callable that transforms args and kwargs used
        as a cache key.

    Returns
    -------
    A decorator which wraps coroutine-like functions with preemptive caching.
    """
    if cache_transform is None:
        key_func = make_key
    else:

        def key_func(args: tuple[t.Any, ...], kwds: dict[t.Any, t.Any]) -> Hashable:
            return make_key(*cache_transform(args, kwds))

    def wrapper(coro: CoroLike[P, R]) -> CoroFunc[P, R]:
        internal_cache: LRU[Hashable, asyncio.Future[R]] = LRU(maxsize)

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.remove, key)

        @wraps(coro)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            key = key_func(args, kwargs)
            if (cached := internal_cache.get(key, None)) is not None:
                return await cached

            c = coro(*args, **kwargs)
            internal_cache[key] = fut = asyncio.ensure_future(c)
            cb = partial(_internal_cache_evict, key)
            fut.add_done_callback(cb)
            return await fut

        return wrapped

    return wrapper
