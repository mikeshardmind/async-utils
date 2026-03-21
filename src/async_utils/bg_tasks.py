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

__lazy_modules__: list[str] = ["asyncio"]

import asyncio
import time
from collections.abc import Callable, Coroutine
from contextvars import Context

from . import _typings as t
from ._as_completed import AsCompletedIterator

type _CoroutineLike[T] = Coroutine[t.Any, t.Any, T]
type _LoopLike = asyncio.AbstractEventLoop | _UnboundLoopSentinel


__all__ = ("BGTasks", "CurrentLoopExecutor")


class _UnboundLoopSentinel:
    """Sentinel for nicer error messages."""

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def create_task(*args: object, **kwargs: object) -> t.Never:
        msg = "Using create_task prior to entering the context is not supported."
        raise RuntimeError(msg)


class BGTasks:
    """An intentionally dumber task group.

    Parameters
    ----------
    exit_timeout: int | None
        Optionally, the number of seconds to wait before sending a
        cancellation to pending tasks. This does not guarantee that after
        the timeout the context manager will exit immediately,
        as tasks may catch cancellation.

        In applications that care about graceful shutdown, this should
        usually not be set. When not provided, the context manager
        will not exit until all tasks have ended.
    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, exit_timeout: float | None) -> None:
        self._tasks: set[asyncio.Task[object]] = set()
        self._etime: float | None = exit_timeout
        self._loop: _LoopLike = _UnboundLoopSentinel()

    def create_task[T](
        self,
        coro: _CoroutineLike[T],
        *,
        name: str | None = None,
        context: Context | None = None,
    ) -> asyncio.Task[T]:
        """Create a task attached to this context manager.

        Returns
        -------
        asyncio.Task: The task that was created.
        """
        t = self._loop.create_task(coro, name=name, context=context)
        if name is not None:
            # See: python/cpython#113050
            # PYUPGRADE: remove this block at python 3.13 minimum
            try:
                set_name = t.set_name
            except AttributeError:
                pass
            else:
                set_name(name)

        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def __aenter__(self: t.Self) -> t.Self:
        self._loop = asyncio.get_running_loop()
        return self

    async def __aexit__(self, *_dont_care: object) -> None:
        start = time.monotonic()
        pending: set[asyncio.Task[t.Any]] = set()
        while tsks := self._tasks.copy():
            if self._etime:
                max_sleep = start - time.monotonic() + self._etime
                if max_sleep <= 0:
                    break

            _done, pending = await asyncio.wait(tsks, timeout=self._etime)
            await asyncio.sleep(0)

        if pending:
            for task in pending:
                task.cancel()
            # This wait is required in case tasks catch cancelation and
            # do further cleanup
            await asyncio.wait(pending)


async def _sem_fut[**P, R](
    sem: asyncio.Semaphore,
    coro_func: Callable[P, _CoroutineLike[R]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    async with sem:
        return await coro_func(*args, **kwargs)


class CurrentLoopExecutor:
    """Provides an API similar to that of concurrent.Futures.Executor

    for running async functions on the current asyncio event loop in
    the current thread.

    Parameters
    ----------

    max_concurrent: int | None
        An optional limit for the number of concurrent submitted function
        calls.

    """

    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def __init__(self, max_concurrent: int | None = None, /) -> None:
        self._sem: asyncio.Semaphore | None = None
        if max_concurrent is not None:
            self._sem = asyncio.Semaphore(max_concurrent)
        self._is_closed: bool = False
        self._loop: _LoopLike = _UnboundLoopSentinel()
        self._futs: set[asyncio.Future[t.Any]] = set()

    async def __aenter__(self) -> t.Self:
        self._loop = asyncio.get_running_loop()
        return self

    async def __aexit__(self, *_dont_case: object) -> None:
        self._is_closed = True
        f = self._futs.copy()
        await asyncio.gather(*f, return_exceptions=True)

    def force_cancel_and_shutdown(self) -> None:
        """Cancels pending tasks and prevents further tasks from being submitted."""
        self._is_closed = True
        for f in self._futs:
            f.cancel()

    def submit[**P, R](
        self,
        fn: Callable[P, _CoroutineLike[R]],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> asyncio.Future[R]:
        """Schedules a coroutine on the current event loop, returning a future."""
        if self._is_closed:
            msg = "Can't submit to a closed or closing executor"
            raise RuntimeError(msg)

        if self._sem:
            f = self._loop.create_task(_sem_fut(self._sem, fn, *args, **kwargs))
        else:
            f = self._loop.create_task(fn(*args, **kwargs))

        self._futs.add(f)
        f.add_done_callback(self._futs.discard)
        return f

    def map[*Ts, R](
        self,
        fn: Callable[[*Ts], _CoroutineLike[R]],
        /,
        *iterables: tuple[*Ts],
    ) -> AsCompletedIterator[R]:
        """Returns an iterator that can be iterated over synchronously or asynchronously.

        When iterated over asynchronously, yields the results directly.
        When iterated over synchronously, yields futures with the results.
        """
        if self._is_closed:
            msg = "Can't submit to a closed or closing executor"
            raise RuntimeError(msg)

        if isinstance(self._loop, _UnboundLoopSentinel):
            msg = "Use this executor as an async context manager"
            raise RuntimeError(msg)  # noqa: TRY004

        if self._sem:
            futs = {
                asyncio.ensure_future(
                    _sem_fut(self._sem, fn, *it),
                    loop=self._loop,
                )
                for it in iterables
            }
        else:
            futs = {asyncio.ensure_future(fn(*it), loop=self._loop) for it in iterables}

        for f in futs:
            self._futs.add(f)
            f.add_done_callback(self._futs.discard)

        return AsCompletedIterator(futs)
