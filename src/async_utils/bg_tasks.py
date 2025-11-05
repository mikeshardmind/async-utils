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
from collections.abc import Coroutine
from contextvars import Context

from . import _typings as t

type _CoroutineLike[T] = Coroutine[t.Any, t.Any, T]
type _LoopLike = asyncio.AbstractEventLoop | _UnboundLoopSentinel


__all__ = ("BGTasks",)


class _UnboundLoopSentinel:
    def __init_subclass__(cls) -> t.Never:
        msg = "Don't subclass this"
        raise RuntimeError(msg)

    __final__ = True

    def create_task(*args: object, **kwargs: object) -> t.Never:
        msg = """
        BGTasks is intended for use as a context manager. Using create_task
        prior to entering the context is not supported.
        """
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
