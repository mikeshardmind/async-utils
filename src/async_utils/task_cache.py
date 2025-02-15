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
import concurrent.futures as cf
from collections.abc import Callable, Coroutine, Hashable
from functools import partial, wraps

from . import _typings as t
from ._paramkey import make_key
from .lru import LRU

__all__ = ("lrutaskcache", "taskcache")


# Use below doesn't accept non-task Futures, so can't accept general awaitables
type CoroFunc[**P, R] = Callable[P, Coroutine[t.Any, t.Any, R]]
type TaskFunc[**P, R] = CoroFunc[P, R] | Callable[P, asyncio.Task[R]]
type TaskCoroFunc[**P, R] = CoroFunc[P, R] | TaskFunc[P, R]

type _CT_RET = tuple[tuple[t.Any, ...], dict[str, t.Any]]

#: Note CacheTransformers recieve a tuple (args) and dict(kwargs)
#: rather than a ParamSpec of the decorated function.
#: Warning: Mutations will impact callsite, return new objects as needed.
type CacheTransformer = Callable[[tuple[t.Any, ...], dict[str, t.Any]], _CT_RET]

type Deco[**P, R] = Callable[[TaskCoroFunc[P, R]], TaskFunc[P, R]]

# Non-annotation assignments for transformed functions
_WRAP_ASSIGN = ("__module__", "__name__", "__qualname__", "__doc__")


def _chain_fut[R](c_fut: cf.Future[R], a_fut: asyncio.Future[R]) -> None:
    if a_fut.cancelled():
        c_fut.cancel()
    elif exc := a_fut.exception():
        c_fut.set_exception(exc)
    else:
        c_fut.set_result(a_fut.result())


class _WrappedSignature[**P, R]:
    #: PYUPGRADE: Ensure inspect.signature still accepts this
    # as func.__signature__
    # Known working: py 3.12.0 - py3.14a5 range inclusive
    def __init__(self, f: TaskCoroFunc[P, R], w: TaskFunc[P, R]) -> None:
        self._f = f
        self._w = w
        self._sig: t.Any | None = None

    def _asyncutils_wrapped_sig(self) -> t.Any:
        if (sig := self._sig) is None:
            import inspect

            sig = inspect.signature(self._f)
            if inspect.iscoroutinefunction(self._f):
                rn: t.Any = sig.return_annotation
                ra = asyncio.Task if rn is inspect.Signature.empty else asyncio.Task[rn]
                sig = sig.replace(return_annotation=ra)
            setattr(self._w, "__signature__", sig)  # noqa: B010
            self._sig = sig
        return sig

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self._asyncutils_wrapped_sig, name)

    def __repr__(self) -> str:
        if self._sig is not None:
            import inspect

            return inspect.Signature.__repr__(self._sig)
        return super().__repr__()

    @property
    def __class__(self) -> type:
        # This is for the isinstance check inspect.signature does.
        import inspect

        self._asyncutils_wrapped_sig()
        return inspect.Signature

    @__class__.setter
    def __class__(self, value: type) -> t.Never:
        raise RuntimeError


async def _await[R](fut: asyncio.Future[R]) -> R:
    return await fut


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
    preemptively cached tasks. The returned function requires an event loop
    be running when it is called despite not being a coroutine itself, but
    does not bind itself to a particular event loop and can be safely shared
    between multiple event loops.
    """
    if cache_transform is None:
        key_func = make_key
    else:

        def key_func(args: tuple[t.Any, ...], kwds: dict[t.Any, t.Any]) -> Hashable:
            return make_key(*cache_transform(args, kwds))

    def wrapper(coro: TaskCoroFunc[P, R]) -> TaskFunc[P, R]:
        internal_cache: dict[Hashable, cf.Future[R]] = {}

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.pop, key)

        @wraps(coro, assigned=_WRAP_ASSIGN)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            key = key_func(args, kwargs)

            ours: cf.Future[R] = cf.Future()
            cached = internal_cache.setdefault(key, ours)

            if cached is not ours:
                fut = asyncio.wrap_future(cached)
                return asyncio.create_task(_await(fut))
            cb = partial(_internal_cache_evict, key)
            ours.add_done_callback(cb)

            c = coro(*args, **kwargs)
            a_fut = asyncio.ensure_future(c)
            a_fut.add_done_callback(partial(_chain_fut, ours))

            return a_fut

        # PYUPGRADE: 3.14.0 recheck, 3.15+
        wrapped.__signature__ = _WrappedSignature(coro, wrapped)  # type: ignore[attr-defined]

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
    preemptively cached tasks. The returned function requires an event loop
    be running when it is called despite not being a coroutine itself, but
    does not bind itself to a particular event loop and can be safely shared
    between multiple event loops.
    """
    if cache_transform is None:
        key_func = make_key
    else:

        def key_func(args: tuple[t.Any, ...], kwds: dict[t.Any, t.Any]) -> Hashable:
            return make_key(*cache_transform(args, kwds))

    def wrapper(coro: TaskCoroFunc[P, R]) -> TaskFunc[P, R]:
        internal_cache: LRU[Hashable, cf.Future[R]] = LRU(maxsize)

        def _internal_cache_evict(key: Hashable, _ignored_task: object) -> None:
            if ttl is not None:
                loop = asyncio.get_running_loop()
                loop.call_later(ttl, internal_cache.remove, key)

        @wraps(coro, assigned=_WRAP_ASSIGN)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> asyncio.Task[R]:
            key = key_func(args, kwargs)

            ours: cf.Future[R] = cf.Future()
            cached = internal_cache.setdefault(key, ours)

            if cached is not ours:
                fut = asyncio.wrap_future(cached)
                return asyncio.create_task(_await(fut))
            cb = partial(_internal_cache_evict, key)
            ours.add_done_callback(cb)

            c = coro(*args, **kwargs)
            a_fut = asyncio.ensure_future(c)
            a_fut.add_done_callback(partial(_chain_fut, ours))

            return a_fut

        # PYUPGRADE: 3.14.0 recheck, 3.15+
        wrapped.__signature__ = _WrappedSignature(coro, wrapped)  # type: ignore[attr-defined]

        return wrapped

    return wrapper
