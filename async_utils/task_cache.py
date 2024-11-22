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
from collections.abc import Callable, Coroutine, Hashable
from functools import partial, wraps
from typing import Any, ParamSpec, TypeVar

from ._cpython_stuff import make_key

__all__ = ("taskcache", "LRU", "lrutaskcache")


P = ParamSpec("P")
T = TypeVar("T")

# Use below doesn't accept non-task Futures, so can't accept general awaitables
type CoroFunc[**P, T] = Callable[P, Coroutine[Any, Any, T]]
type TaskFunc[**P, T] = CoroFunc[P, T] | Callable[P, asyncio.Task[T]]
type TaskCoroFunc[**P, T] = CoroFunc[P, T] | TaskFunc[P, T]


class LRU[K, V]:
    def __init__(self, maxsize: int, /):
        self.cache: dict[K, V] = {}
        self.maxsize = maxsize

    def get(self, key: K, default: T, /) -> V | T:
        if key not in self.cache:
            return default
        self.cache[key] = self.cache.pop(key)
        return self.cache[key]

    def __getitem__(self, key: K, /) -> V:
        self.cache[key] = self.cache.pop(key)
        return self.cache[key]

    def __setitem__(self, key: K, value: V, /):
        self.cache[key] = value
        if len(self.cache) > self.maxsize:
            self.cache.pop(next(iter(self.cache)))

    def remove(self, key: K, /) -> None:
        self.cache.pop(key, None)


def taskcache(
    ttl: float | None = None,
) -> Callable[[TaskCoroFunc[P, T]], TaskFunc[P, T]]:
    """Decorator to modify coroutine functions to instead act as functions returning cached tasks.

    For general use, this leaves the end user API largely the same,
    while leveraging tasks to allow preemptive caching.

    Note: This uses the args and kwargs of the original coroutine function as a cache key.
    This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when feasible in cases where this may matter.

    The ordering of args and kwargs matters."""

    def wrapper(coro: TaskCoroFunc[P, T]) -> TaskFunc[P, T]:
        internal_cache: dict[Hashable, asyncio.Task[T]] = {}

        @wraps(coro, assigned=("__module__", "__name__", "__qualname__", "__doc__"))
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
            key = make_key(args, kwargs)
            try:
                return internal_cache[key]
            except KeyError:
                internal_cache[key] = task = asyncio.ensure_future(coro(*args, **kwargs))
                if ttl is not None:
                    # This results in internal_cache.pop(key, task) later
                    # while avoiding a late binding issue with a lambda instead
                    call_after_ttl = partial(
                        asyncio.get_running_loop().call_later,
                        ttl,
                        internal_cache.pop,
                        key,
                    )
                    task.add_done_callback(call_after_ttl)
                return task

        return wrapped

    return wrapper


def _lru_evict(ttl: float, cache: LRU[Hashable, Any], key: Hashable, _ignored_task: object) -> None:
    asyncio.get_running_loop().call_later(ttl, cache.remove, key)


def lrutaskcache(ttl: float | None = None, maxsize: int = 1024) -> Callable[[TaskCoroFunc[P, T]], TaskFunc[P, T]]:
    """Decorator to modify coroutine functions to instead act as functions returning cached tasks.

    For general use, this leaves the end user API largely the same,
    while leveraging tasks to allow preemptive caching.

    Note: This uses the args and kwargs of the original coroutine function as a cache key.
    This includes instances (self) when wrapping methods.
    Consider not wrapping instance methods, but what those methods call when feasible in cases where this may matter.

    The ordering of args and kwargs matters.

    tasks are evicted by LRU and ttl.
    """

    def wrapper(coro: TaskCoroFunc[P, T]) -> TaskFunc[P, T]:
        internal_cache: LRU[Hashable, asyncio.Task[T]] = LRU(maxsize)

        @wraps(coro, assigned=("__module__", "__name__", "__qualname__", "__doc__"))
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[T]:
            key = make_key(args, kwargs)
            try:
                return internal_cache[key]
            except KeyError:
                internal_cache[key] = task = asyncio.ensure_future(coro(*args, **kwargs))
                if ttl is not None:
                    task.add_done_callback(partial(_lru_evict, ttl, internal_cache, key))
                return task

        return wrapped

    return wrapper
