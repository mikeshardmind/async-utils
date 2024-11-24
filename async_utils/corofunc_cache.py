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
from typing import Any, ParamSpec, TypeVar

from ._cpython_stuff import make_key
from .lru import LRU

__all__ = ("corocache", "lrucorocache")


P = ParamSpec("P")
R = TypeVar("R")


type CoroFunc[**P, R] = Callable[P, Coroutine[Any, Any, R]]
type CoroLike[**P, R] = Callable[P, Awaitable[R]]


def corocache(
    ttl: float | None = None,
) -> Callable[[CoroLike[P, R]], CoroFunc[P, R]]:
    """Cache the results of the decorated coroutine.

    This is less powerful than the version in task_cache.py but may work better
    for some cases where typing of libraries this interacts with is too
    restrictive.

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
    A decorator which wraps coroutine-like functions with preemptive caching.
    """

    def wrapper(coro: CoroLike[P, R]) -> CoroFunc[P, R]:
        internal_cache: dict[Hashable, asyncio.Future[R]] = {}

        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            key = make_key(args, kwargs)
            try:
                return await internal_cache[key]
            except KeyError:
                internal_cache[key] = fut = asyncio.ensure_future(
                    coro(*args, **kwargs)
                )
                if ttl is not None:
                    # This results in internal_cache.pop(key, fut) later
                    # while avoiding a late binding issue with a lambda instead
                    call_after_ttl = partial(
                        asyncio.get_running_loop().call_later,
                        ttl,
                        internal_cache.pop,
                        key,
                    )
                    fut.add_done_callback(call_after_ttl)
                return await fut

        return wrapped

    return wrapper


def _lru_evict(
    ttl: float, cache: LRU[Hashable, Any], key: Hashable, _ignored_fut: object
) -> None:
    asyncio.get_running_loop().call_later(ttl, cache.remove, key)


def lrucorocache(
    ttl: float | None = None, maxsize: int = 1024
) -> Callable[[CoroLike[P, R]], CoroFunc[P, R]]:
    """Cache the results of the decorated coroutine.

    This is less powerful than the version in task_cache.py but may work better
    for some cases where typing of libraries this interacts with is too
    restrictive.

    Note: This uses the args and kwargs of the original coroutine function as a
    cache key. This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when
    feasible in cases where this may matter.

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

    Returns
    -------
    A decorator which wraps coroutine-like functions with preemptive caching.
    """

    def wrapper(coro: CoroLike[P, R]) -> CoroFunc[P, R]:
        internal_cache: LRU[Hashable, asyncio.Future[R]] = LRU(maxsize)

        @wraps(coro)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            key = make_key(args, kwargs)
            try:
                return await internal_cache[key]
            except KeyError:
                internal_cache[key] = fut = asyncio.ensure_future(
                    coro(*args, **kwargs)
                )
                if ttl is not None:
                    fut.add_done_callback(
                        partial(_lru_evict, ttl, internal_cache, key)
                    )
                return await fut

        return wrapped

    return wrapper
